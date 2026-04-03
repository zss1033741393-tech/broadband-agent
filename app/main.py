from contextlib import asynccontextmanager

import gradio as gr
from fastapi import FastAPI

from app.api.routes import router
from app.db.database import init_db
from app.logger import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动初始化 + 关闭清理"""
    setup_logging()
    await init_db()
    yield


app = FastAPI(
    title="家宽体验感知优化 Agent",
    description="家庭宽带用户体验优化 Agent Pipeline 原型",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


# 挂载 Gradio UI
# Gradio 6 废弃了 app.mount()，改用 gr.mount_gradio_app()
def mount_gradio() -> None:
    try:
        from ui.chat_ui import build_ui

        gradio_app = build_ui()
        gr.mount_gradio_app(app, gradio_app, path="/ui")
    except ImportError:
        pass


mount_gradio()
