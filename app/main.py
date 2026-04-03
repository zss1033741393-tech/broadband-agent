"""FastAPI 入口 + Gradio 挂载"""
import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import load_logging_config
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化日志和数据库
    logging.config.dictConfig(load_logging_config())
    await init_db()
    yield


app = FastAPI(
    title="家宽体验感知优化 Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


# 挂载 Gradio 调试界面
def mount_gradio() -> None:
    """将 Gradio UI 挂载到 /ui 路径"""
    try:
        import gradio as gr

        from ui.chat_ui import create_ui
        from app.agent.agent import BroadbandAgent

        agent = BroadbandAgent()
        gradio_app = create_ui(agent)
        app.mount("/ui", gr.mount_gradio_app(app, gradio_app, path="/ui"))
    except ImportError:
        logging.getLogger("app").warning("Gradio 未安装，跳过 UI 挂载")


mount_gradio()
