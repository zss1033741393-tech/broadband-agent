import copy
import json
import os
from typing import Any

from app.db.crud import save_plan_result


def load_template(template_name: str) -> dict:
    """读取指定方案的 JSON 模板

    Args:
        template_name: 模板名称，如 "cei_perception_plan"、"user_profile"

    Returns:
        模板 JSON dict，文件不存在时返回空 dict
    """
    template_path = f"templates/{template_name}.json"
    if not os.path.exists(template_path):
        return {}
    with open(template_path, encoding="utf-8") as f:
        return json.load(f)


def fill_template(template: dict, params: dict) -> dict:
    """将参数填充到模板中（深度合并）

    Args:
        template: 原始模板 dict
        params: 需要覆盖的参数 dict（支持嵌套路径用 "." 分隔）

    Returns:
        填充后的 dict
    """
    result = copy.deepcopy(template)
    _deep_merge(result, params)
    return result


def _deep_merge(base: dict, override: dict) -> None:
    """递归合并 override 到 base（就地修改 base）"""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


def set_nested_value(data: dict, dot_path: str, value: Any) -> None:
    """按点分隔路径设置嵌套字段值

    Args:
        data: 目标 dict
        dot_path: 字段路径，如 "warning_threshold.latency_ms"
        value: 要设置的值
    """
    keys = dot_path.split(".")
    cur = data
    for key in keys[:-1]:
        if key not in cur:
            cur[key] = {}
        cur = cur[key]
    cur[keys[-1]] = value


async def save_plan(session_id: str, plan: dict, retry_count: int = 0) -> dict:
    """保存生成的方案到数据库

    Args:
        session_id: 会话 ID
        plan: 方案 dict（PlanFillResult 格式）
        retry_count: 当前重试次数

    Returns:
        {"success": True}
    """
    await save_plan_result(session_id, plan, retry_count)
    return {"success": True}
