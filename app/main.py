import os
from contextlib import asynccontextmanager

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


# 挂载 Gradio UI（可选，需安装 gradio）
def mount_gradio() -> None:
    try:
        import gradio as gr
        from ui.chat_ui import build_ui

        gradio_app = build_ui()
        # 将 Gradio 挂载到 /ui 路径
        app.mount("/ui", gradio_app)
    except ImportError:
        pass


mount_gradio()
