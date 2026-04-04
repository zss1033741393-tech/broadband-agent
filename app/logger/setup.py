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
