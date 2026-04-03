"""意图解析 Skill 单元测试"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.intent_parsing.scripts.parse_intent import (
    generate_followup_questions,
    load_intent_schema,
    merge_with_profile,
    validate_intent,
)


def test_load_intent_schema() -> None:
    schema = load_intent_schema()
    assert "intent_goal" in schema
    assert "required_fields" in schema


def test_validate_intent_complete() -> None:
    intent = {
        "user_type": "直播用户",
        "scenario": "上行带宽保障",
        "guarantee_target": {"priority_level": "high", "sensitivity": "卡顿", "key_applications": []},
    }
    is_complete, missing = validate_intent(intent)
    assert is_complete
    assert missing == []


def test_validate_intent_missing_fields() -> None:
    intent = {"user_type": "游戏用户"}
    is_complete, missing = validate_intent(intent)
    assert not is_complete
    assert "scenario" in missing


def test_generate_followup_questions() -> None:
    questions = generate_followup_questions(["user_type", "scenario"])
    assert len(questions) > 0
    assert isinstance(questions, str)


def test_merge_with_profile() -> None:
    intent = {"user_type": "", "scenario": "低延迟保障"}
    profile = {"user_profile": {"user_type": "游戏用户"}}
    merged = merge_with_profile(intent, profile)
    assert merged["user_type"] == "游戏用户"
    assert merged["scenario"] == "低延迟保障"  # 非空字段不被覆盖
