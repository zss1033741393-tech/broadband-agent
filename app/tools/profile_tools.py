import json
from typing import Optional

from app.db.crud import get_user_profile, save_user_profile as db_save_user_profile


async def load_user_profile(user_id: str) -> dict:
    """从数据库加载用户历史画像

    Args:
        user_id: 用户 ID

    Returns:
        用户画像 dict，包含 profile、app_history、network_kpi；无记录时返回空结构
    """
    data = await get_user_profile(user_id)
    if data:
        return data
    # 返回空画像结构
    return {
        "profile": {
            "user_type": "",
            "scenario": "",
            "guarantee_period": {},
            "guarantee_target": {},
            "core_metrics": {},
        },
        "app_history": {},
        "network_kpi": {},
    }


async def save_user_profile(
    user_id: str,
    profile: dict,
    app_history: Optional[dict] = None,
    network_kpi: Optional[dict] = None,
) -> dict:
    """保存用户画像到数据库

    Args:
        user_id: 用户 ID
        profile: 用户画像 dict
        app_history: 应用行为历史（可选）
        network_kpi: 网络 KPI 数据（可选）

    Returns:
        {"success": True}
    """
    await db_save_user_profile(user_id, profile, app_history, network_kpi)
    return {"success": True}


async def query_app_history(user_id: str) -> dict:
    """查询用户应用行为历史

    Args:
        user_id: 用户 ID

    Returns:
        应用行为历史 dict，包含 key_guarantee_apps、perception_trigger_time 等
    """
    data = await get_user_profile(user_id)
    return data.get("app_history", {}) if data else {}


async def query_network_kpi(user_id: str, time_range: str = "7d") -> dict:
    """查询用户网络 KPI 数据

    Args:
        user_id: 用户 ID
        time_range: 查询时间范围，如 "7d"、"30d"

    Returns:
        网络 KPI dict，包含 periodic_power_off、periodic_behavior_pattern 等
    """
    data = await get_user_profile(user_id)
    return data.get("network_kpi", {}) if data else {}
