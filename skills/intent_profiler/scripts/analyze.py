from __future__ import annotations

"""意图校验脚本 — 纯结构/枚举/逻辑一致性校验。

职责：
1. 必填字段存在性检查
2. 枚举值合法性检查
3. 套餐与场景组合合法性检查
4. 保障时段完整性检查

不做：意图提取、字段推断、追问话术生成（这些由 LLM 在 Prompt 层完成）。
"""

import json
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parent.parent
SCHEMA_PATH = SKILL_DIR / "references" / "intent_schema.json"
TEMPLATE_PATH = SKILL_DIR / "references" / "profile_template.json"


# ── 数据加载 ────────────────────────────────────────────────────────────────


def load_intent_schema() -> dict[str, Any]:
    """加载意图目标结构定义（含枚举、必填字段、合法组合）"""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_profile_template() -> dict[str, Any]:
    """加载用户画像模板"""
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


# ── 校验 ────────────────────────────────────────────────────────────────────


def validate_intent(intent_goal: dict[str, Any]) -> tuple[bool, list[str]]:
    """校验意图目标，返回 (是否完整, 缺失/非法字段列表)。

    检查项：
    1. required_fields 是否有值
    2. user_type / package_type / scenario / guarantee_object 枚举合法性
    3. package_type ↔ scenario 组合合法性
    4. guarantee_period 完整性（is_all_day=true 或 start_time+end_time 均有值）
    """
    schema = load_intent_schema()
    missing: list[str] = []

    # 1. 必填字段存在性
    for field in schema.get("required_fields", []):
        value = intent_goal.get(field)
        if not value:
            missing.append(field)
        elif isinstance(value, dict) and not any(v for v in value.values()):
            missing.append(field)

    # 2. 枚举合法性
    enum_fields = {
        "user_type": ["主播用户", "游戏用户", "VVIP用户"],
        "package_type": ["普通套餐", "直播套餐", "专线套餐"],
        "scenario": ["家庭直播用户", "卖场走播场景", "楼宇直播"],
        "guarantee_object": ["家庭网络", "STA级", "整网"],
    }
    for field, valid_values in enum_fields.items():
        val = intent_goal.get(field)
        if val and val not in valid_values and field not in missing:
            missing.append(field)

    # 3. 套餐与场景组合合法性
    package = intent_goal.get("package_type", "")
    scenario = intent_goal.get("scenario", "")
    if package and scenario:
        combos = schema.get("valid_combinations", {})
        allowed_scenarios = combos.get(package, {}).get("scenarios", [])
        if allowed_scenarios and scenario not in allowed_scenarios:
            missing.append("scenario_package_mismatch")

    # 4. 保障时段完整性
    period = intent_goal.get("guarantee_period", {})
    if isinstance(period, dict) and "guarantee_period" not in missing:
        is_all_day = period.get("is_all_day", False)
        if not is_all_day:
            if not period.get("start_time") or not period.get("end_time"):
                if "guarantee_period" not in missing:
                    missing.append("guarantee_period")

    return len(missing) == 0, list(dict.fromkeys(missing))  # 去重保序


# ── CLI 入口 ────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    """供 get_skill_script(execute=True) 调用

    用法:
        python analyze.py '<intent_goal_json>'

    输出: JSON，含 complete / intent_goal / profile / missing_fields / schema
    """
    import sys

    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        intent_goal = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        intent_goal = {}

    complete, missing = validate_intent(intent_goal)
    profile = load_profile_template()

    # 将已知意图字段同步到 profile.user_profile（便于下游读取）
    if isinstance(intent_goal, dict):
        for key, val in intent_goal.items():
            if val and key in profile["user_profile"]:
                profile["user_profile"][key] = val

    print(json.dumps({
        "complete": complete,
        "intent_goal": intent_goal,
        "profile": profile,
        "missing_fields": missing,
        "schema": load_intent_schema(),
    }, ensure_ascii=False))
