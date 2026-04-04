"""AgentOS 入口 + Gradio 调试界面挂载

启动：uvicorn app.main:app --port 8000

端点：
  GET  /           → AgentOS API 信息（JSON）
  GET  /docs       → Swagger API 文档
  GET  /gradio     → Gradio 对话调试界面
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
# 自动提供：REST API、会话管理、Trace 可视化
# ─────────────────────────────────────────────────────────────

agent_os = AgentOS(
    agents=[get_agent()],
    db=SqliteDb(db_file=_cfg.storage.sqlite_db_path),
    tracing=True,
)

app = agent_os.get_app()


# ─────────────────────────────────────────────────────────────
# Gradio 调试界面 — 挂载到 /gradio
# ─────────────────────────────────────────────────────────────

def _mount_gradio() -> None:
    try:
        import gradio as gr
        from ui.chat_ui import create_ui
    except ImportError as e:
        logger.info("Gradio 未安装，跳过调试界面挂载: %s", e)
        return

    gr.mount_gradio_app(app, create_ui(), path="/gradio")
    logger.info("Gradio 调试界面已挂载: /gradio")


_mount_gradio()

