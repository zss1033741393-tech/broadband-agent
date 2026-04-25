"""引擎选择配置。

支持运行时切换 agno / opencode 两个引擎，配置持久化到 data/engine.json。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "engine.json"
_DEFAULT: dict[str, Any] = {
    "engine": "agno",
    "opencode_url": "http://127.0.0.1:4096",
    "opencode_agent": "orchestrator",
}


def get_config() -> dict[str, Any]:
    """读取引擎配置，不存在时返回默认值。"""
    if _CONFIG_PATH.exists():
        return {**_DEFAULT, **json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))}
    return dict(_DEFAULT)


def set_config(patch: dict[str, Any]) -> dict[str, Any]:
    """合并更新引擎配置并持久化。"""
    cfg = get_config()
    cfg.update(patch)
    _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg
