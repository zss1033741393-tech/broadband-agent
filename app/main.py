"""AgentOS 入口

启动：uvicorn app.main:app --port 8000

端点：
  GET  /      → AgentOS API 信息（JSON）
  GET  /docs  → Swagger API 文档

Gradio 调试界面独立运行，避免与 AgentOS TrailingSlashMiddleware 冲突：
  python ui/chat_ui.py   → http://localhost:7860
"""
from __future__ import annotations

import logging

from agno.db.sqlite import SqliteDb
from agno.os import AgentOS

from app.agent.agent import get_agent
from app.config import load_config
from app.logger.setup import setup_logging

setup_logging()

_cfg = load_config()

logger = logging.getLogger("app")

agent_os = AgentOS(
    agents=[get_agent()],
    db=SqliteDb(db_file=_cfg.storage.sqlite_db_path),
    tracing=True,
)

app = agent_os.get_app()
