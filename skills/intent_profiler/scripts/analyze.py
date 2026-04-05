#!/usr/bin/env python3
"""意图解析与画像补全 — 合并脚本

流程：提取意图字段 → 加载画像模板 → 用历史数据推断补全 → 校验完整性 → 生成追问。
"""
import json
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parent.parent
SCHEMA_PATH = SKILL_DIR / "references" / "intent_schema.json"
TEMPLATE_PATH = SKILL_DIR / "references" / "profile_template.json"
RULES_PATH = SKILL_DIR / "references" / "field_rules.md"


# ── 数据加载 ────────────────────────────────────────────────

def load_intent_schema() -> dict[str, Any]:
    """加载意图目标结构定义"""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_profile_template() -> dict[str, Any]:
    """加载用户画像模板"""
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def load_field_rules() -> str:
    """加载字段补全规则（Markdown 文本）"""
    return RULES_PATH.read_text(encoding="utf-8")


# ── 画像推断 ────────────────────────────────────────────────

def infer_from_app_history(
    profile: dict[str, Any],
    app_list: list[str],
) -> dict[str, Any]:
    """根据应用列表推断用户画像字段"""
    live_apps = {"obs", "obs studio", "抖音直播伴侣", "虎牙直播"}
    game_apps = {"steam", "wegame", "战网", "英雄联盟", "王者荣耀"}
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


def merge_intent_with_profile(
    intent_goal: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """将画像数据合并到意图目标，只填充 intent_goal 中为空的字段"""
    merged = dict(intent_goal)
    profile_data = profile.get("user_profile", {})
    for key, value in profile_data.items():
        if not merged.get(key) and value:
            merged[key] = value
    return merged


# ── 意图校验 ────────────────────────────────────────────────

def validate_intent(intent_goal: dict[str, Any]) -> tuple[bool, list[str]]:
    """校验意图目标完整性，返回 (是否完整, 缺失字段列表)"""
    schema = load_intent_schema()
    required = schema.get("required_fields", [])
    missing = [f for f in required if not intent_goal.get(f)]
    return len(missing) == 0, missing


def check_profile_missing(profile: dict[str, Any]) -> list[str]:
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


# ── 追问生成 ────────────────────────────────────────────────

def generate_followup_questions(missing_fields: list[str]) -> str:
    """根据缺失字段生成自然语言追问"""
    field_questions: dict[str, str] = {
        "user_type": "请问您主要是用来做什么的？（例如：直播、游戏、视频会议）",
        "scenario": "您希望优化哪方面的网络体验？（如：上行带宽、低延迟、稳定性）",
        "guarantee_target": "您对网络问题最敏感的是哪方面？（卡顿、延迟还是断线）",
        "guarantee_period": "您一般什么时间段需要重点保障网络？",
    }
    questions = [field_questions[f] for f in missing_fields if f in field_questions]
    if not questions:
        return ""
    if len(questions) == 1:
        return questions[0]
    return "为了更好地配置方案，我需要了解几个信息：\n" + "\n".join(
        f"{i+1}. {q}" for i, q in enumerate(questions)
    )


# ── CLI 入口 ────────────────────────────────────────────────

if __name__ == "__main__":
    """供 get_skill_script(execute=True) 调用

    用法:
        python analyze.py '<intent_goal_json>'

    输出: JSON，含 complete / intent_goal / profile / missing_fields / followup / schema
    """
    import sys

    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        intent_goal = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        intent_goal = {}

    # 1. 加载画像模板，用已知意图字段填充
    profile = load_profile_template()
    profile["user_profile"].update(
        {k: v for k, v in intent_goal.items() if v}
    )

    # 2. 将画像推断结果合并回意图
    intent_goal = merge_intent_with_profile(intent_goal, profile)

    # 3. 校验意图完整性
    complete, missing = validate_intent(intent_goal)
    followup = generate_followup_questions(missing) if not complete else ""
    schema = load_intent_schema()

    print(json.dumps({
        "complete": complete,
        "intent_goal": intent_goal,
        "profile": profile,
        "missing_fields": missing,
        "followup": followup,
        "schema": schema,
    }, ensure_ascii=False))
