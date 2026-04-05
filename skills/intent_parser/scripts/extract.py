#!/usr/bin/env python3
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


if __name__ == "__main__":
    """CLI 入口 — 供 get_skill_script(execute=True) 调用

    用法:
        python extract.py '<intent_goal_json>'

    输出: JSON 字符串，含 complete / missing_fields / followup / schema
    """
    import sys

    intent_goal_json = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        intent_goal = json.loads(intent_goal_json) if intent_goal_json.strip() else {}
    except json.JSONDecodeError:
        intent_goal = {}

    complete, missing = validate_intent(intent_goal)
    followup = generate_followup_questions(missing) if not complete else ""
    schema = load_intent_schema()

    print(json.dumps(
        {"complete": complete, "missing_fields": missing, "followup": followup, "schema": schema},
        ensure_ascii=False,
    ))
