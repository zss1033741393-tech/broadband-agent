"""意图解析核心脚本"""
import json
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parent.parent
SCHEMA_PATH = SKILL_DIR / "references" / "intent_schema.json"


def load_intent_schema() -> dict[str, Any]:
    """加载意图目标结构定义"""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_intent(intent_goal: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    校验意图目标完整性。

    Returns:
        (是否完整, 缺失字段列表)
    """
    schema = load_intent_schema()
    required = schema.get("required_fields", [])
    missing = [f for f in required if not intent_goal.get(f)]
    return len(missing) == 0, missing


def merge_with_profile(
    intent_goal: dict[str, Any],
    user_profile: dict[str, Any],
) -> dict[str, Any]:
    """
    将用户画像数据合并到意图目标中，补全缺失字段。
    只填充 intent_goal 中为空的字段。
    """
    merged = dict(intent_goal)
    profile_data = user_profile.get("user_profile", {})
    for key, value in profile_data.items():
        if not merged.get(key) and value:
            merged[key] = value
    return merged


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
