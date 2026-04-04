"""日志初始化 — 从 logging.yaml 加载配置，确保 logs/ 目录存在"""
from __future__ import annotations

import logging
import logging.config
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "logging.yaml"
_LOGS_DIR = Path(__file__).parent.parent.parent / "logs"


def setup_logging() -> None:
    """加载 logging.yaml，创建 logs/ 目录，初始化日志配置。幂等，重复调用安全。"""
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if not _CONFIG_PATH.exists():
        logging.basicConfig(level=logging.INFO)
        return

    with open(_CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logging.config.dictConfig(config)
    _attach_agno_file_handler()


def _attach_agno_file_handler() -> None:
    """将 Agno 内部日志同步写入 logs/agent.log

    Agno 使用名为 "agno" 的 AgnoLogger，已附加 RichHandler（控制台彩色输出），
    且 propagate=False，不会到达 root logger 或 "agent" logger。
    此处手动追加 FileHandler，使 debug_mode=True 的详细日志落盘。
    """
    agno_logger = logging.getLogger("agno")
    # 幂等：已有 FileHandler 则跳过
    if any(isinstance(h, logging.FileHandler) for h in agno_logger.handlers):
        return

    fh = logging.FileHandler(_LOGS_DIR / "agent.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        fmt="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    agno_logger.addHandler(fh)
