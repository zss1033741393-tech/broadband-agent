"""自定义输出护栏 — 校验 Agent 输出的配置 JSON 格式"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("guardrails")

# 设备配置必须包含的顶层字段
_REQUIRED_CONFIG_KEYS = {"device_type", "parameters"}


def validate_config(config: dict[str, Any]) -> bool:
    """校验单个设备配置是否包含必要字段"""
    return all(k in config for k in _REQUIRED_CONFIG_KEYS)


def validate_config_output(configs: dict[str, Any]) -> list[str]:
    """校验 config_translator 返回的所有配置，返回失败的配置名列表"""
    failed = []
    for name, config in configs.items():
        if not isinstance(config, dict) or not validate_config(config):
            failed.append(name)
            logger.warning("配置 %s 格式校验失败: %s", name, config)
    return failed
