"""配置加载模块 — 从 YAML 文件读取所有配置"""
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).parent.parent / "configs"


def _load_yaml(filename: str) -> dict[str, Any]:
    """加载指定 YAML 配置文件"""
    path = CONFIG_DIR / filename
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_llm_config() -> dict[str, Any]:
    """加载 LLM 模型配置"""
    return _load_yaml("llm.yaml")


def load_pipeline_config() -> dict[str, Any]:
    """加载运行参数配置"""
    return _load_yaml("pipeline.yaml")


def load_logging_config() -> dict[str, Any]:
    """加载日志配置"""
    return _load_yaml("logging.yaml")


def get_model_config(tier: str = "main") -> dict[str, Any]:
    """获取指定 tier 的模型配置"""
    llm_cfg = load_llm_config()
    default = llm_cfg.get("default", "main")
    models = llm_cfg.get("models", {})
    return models.get(tier, models.get(default, {}))
