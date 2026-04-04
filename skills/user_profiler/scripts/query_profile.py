#!/usr/bin/env python3
"""用户画像查询与补全脚本"""
import json
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parent.parent
TEMPLATE_PATH = SKILL_DIR / "references" / "profile_template.json"
RULES_PATH = SKILL_DIR / "references" / "field_rules.md"


def load_profile_template() -> dict[str, Any]:
    """加载用户画像模板"""
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def load_field_rules() -> str:
    """加载字段补全规则"""
    return RULES_PATH.read_text(encoding="utf-8")


def get_empty_profile() -> dict[str, Any]:
    """返回空白用户画像（原型阶段使用，生产阶段应从数据库查询）"""
    return load_profile_template()


def infer_from_app_history(
    profile: dict[str, Any],
    app_list: list[str],
) -> dict[str, Any]:
    """
    根据应用列表推断用户画像字段。

    Args:
        profile: 当前用户画像
        app_list: 用户活跃应用列表

    Returns:
        更新后的用户画像
    """
    # 直播应用特征
    live_apps = {"obs", "obs studio", "抖音直播伴侣", "虎牙直播"}
    # 游戏应用特征
    game_apps = {"steam", "wegame", "战网", "英雄联盟", "王者荣耀"}
    # 办公应用特征
    office_apps = {"钉钉", "腾讯会议", "zoom", "飞书", "teams"}

    app_set = {a.lower() for a in app_list}
    up_profile = dict(profile)
    up_core = dict(up_profile.get("user_profile", {}).get("core_metrics", {}))

    if app_set & live_apps:
        up_profile.setdefault("user_profile", {})["user_type"] = "直播用户"
        up_core["bandwidth_priority"] = True
    elif app_set & game_apps:
        up_profile.setdefault("user_profile", {})["user_type"] = "游戏用户"
        up_core["latency_sensitive"] = True
    elif app_set & office_apps:
        up_profile.setdefault("user_profile", {})["user_type"] = "办公用户"
        up_core["stability_priority"] = True

    up_profile.setdefault("user_profile", {})["core_metrics"] = up_core
    return up_profile


def check_missing_fields(profile: dict[str, Any]) -> list[str]:
    """检查画像中哪些关键字段仍然缺失"""
    user_profile = profile.get("user_profile", {})
    missing = []
    if not user_profile.get("user_type"):
        missing.append("user_type")
    if not user_profile.get("scenario"):
        missing.append("scenario")
    period = user_profile.get("guarantee_period", {})
    if not period.get("start_time") or period.get("start_time") == "":
        missing.append("guarantee_period")
    return missing


if __name__ == "__main__":
    """CLI 入口 — 供 get_skill_script(execute=True) 调用

    用法:
        python query_profile.py '<known_info_json>'

    输出: JSON 字符串，含 template / missing_fields / field_rules
    """
    import sys

    known_info_json = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        known = json.loads(known_info_json) if known_info_json.strip() else {}
    except json.JSONDecodeError:
        known = {}

    profile = get_empty_profile()
    profile["user_profile"].update(known)
    missing = check_missing_fields(profile)
    rules = load_field_rules()

    print(json.dumps(
        {"template": profile, "missing_fields": missing, "field_rules": rules},
        ensure_ascii=False,
    ))
