"""AgentOS 入口 + 可选 Gradio 调试界面挂载

启动：uvicorn app.main:app --port 8000
- AgentOS API:   http://localhost:8000
- Gradio 调试:   http://localhost:8000/gradio（如已安装 gradio）
"""
from __future__ import annotations

import logging

from agno.db.sqlite import SqliteDb
from agno.os import AgentOS

from app.agent.agent import get_agent
from app.config import load_config

_cfg = load_config()

logger = logging.getLogger("app")

# ─────────────────────────────────────────────────────────────
# AgentOS — 替代手写 FastAPI + Tracer
# 自动提供：REST/WS API、会话管理、Trace 可视化、内置 Web UI
# ─────────────────────────────────────────────────────────────

agent_os = AgentOS(
    agents=[get_agent()],
    db=SqliteDb(db_file=_cfg.storage.sqlite_db_path),  # AgentOS 级别会话持久化
    tracing=True,      # 原生链路追踪，连接 os.agno.com 可视化
)

app = agent_os.get_app()


# ─────────────────────────────────────────────────────────────
# 可选：挂载 Gradio 调试界面
# ─────────────────────────────────────────────────────────────

def _mount_gradio() -> None:
    """将 Gradio UI 挂载到 /gradio 路径（依赖可选）"""
    try:
        import gradio as gr
    except ImportError:
        logger.info("Gradio 未安装，跳过调试界面挂载")
        return

    def chat(message: str, history: list) -> str:
        """Gradio 流式对话函数"""
        response = ""
        try:
            for chunk in get_agent().run(message, stream=True):
                if hasattr(chunk, "content") and chunk.content:
                    response += chunk.content
            return response
        except Exception as exc:
            logger.error("Agent 运行异常: %s", exc)
            return f"[错误] {exc}"

    gradio_app = gr.ChatInterface(
        fn=chat,
        title="家宽体验感知优化 Agent — 调试界面",
        description="在此界面调试 Agent 对话流程。生产环境请使用 AgentOS API。",
    )
    gr.mount_gradio_app(app, gradio_app, path="/gradio")
    logger.info("Gradio 调试界面已挂载: /gradio")


_mount_gradio()
