"""会话隔离与生命周期管理。

每个 Gradio session_hash → 独立 Agent 实例 + Tracer。
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from loguru import logger

from agno.agent import Agent

from core.agent_factory import create_agent
from core.model_loader import inject_prompt_tracer
from core.observability.db import db
from core.observability.tracer import Tracer


@dataclass
class SessionContext:
    """一个会话的完整上下文。"""
    session_hash: str
    agent: Agent
    tracer: Tracer
    db_session_id: Optional[int] = None
    slot_state: Dict[str, Any] = field(default_factory=dict)
    task_type: Optional[str] = None  # comprehensive / specific / insight


class SessionManager:
    """管理所有活跃会话。"""

    def __init__(self):
        self._sessions: Dict[str, SessionContext] = {}
        logger.info("SessionManager 初始化完成")

    def get_or_create(self, session_hash: str) -> SessionContext:
        """获取或创建会话上下文。"""
        if session_hash in self._sessions:
            return self._sessions[session_hash]

        # 创建 DB 记录
        db_sid = db.create_session(session_hash)

        # 创建 Agent (使用 session_hash 作为 agno session_id)
        agent = create_agent(session_id=session_hash)

        # 创建 Tracer，并向 model 注入 prompt 追踪回调
        tracer = Tracer(session_hash, db_session_id=db_sid)
        try:
            inject_prompt_tracer(agent.model, tracer.llm_prompt)
        except Exception:
            logger.warning("inject_prompt_tracer 失败，prompt 追踪不可用")

        ctx = SessionContext(
            session_hash=session_hash,
            agent=agent,
            tracer=tracer,
            db_session_id=db_sid,
        )
        self._sessions[session_hash] = ctx
        logger.info(f"会话 {session_hash[:8]}... 创建成功")
        return ctx

    def destroy(self, session_hash: str) -> None:
        """销毁会话并持久化元数据。"""
        ctx = self._sessions.pop(session_hash, None)
        if ctx:
            db.end_session(session_hash, task_type=ctx.task_type or "")
            logger.info(f"会话 {session_hash[:8]}... 销毁")

    def get(self, session_hash: str) -> Optional[SessionContext]:
        return self._sessions.get(session_hash)

    @property
    def active_count(self) -> int:
        return len(self._sessions)


# 全局单例
session_manager = SessionManager()
