"""intent_profiler Skill 单元测试（合并后的意图解析+画像补全）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.intent_profiler.scripts.analyze import (
    check_profile_missing,
    generate_followup_questions,
    infer_from_app_history,
    load_intent_schema,
    load_profile_template,
    merge_intent_with_profile,
    validate_intent,
)


def test_load_intent_schema() -> None:
    schema = load_intent_schema()
    assert "intent_goal" in schema
    assert "required_fields" in schema


def test_load_profile_template() -> None:
    template = load_profile_template()
    assert "user_profile" in template
    assert "application_history" in template
    assert "network_kpi" in template


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


def test_merge_intent_with_profile() -> None:
    intent = {"user_type": "", "scenario": "低延迟保障"}
    profile = {"user_profile": {"user_type": "游戏用户"}}
    merged = merge_intent_with_profile(intent, profile)
    assert merged["user_type"] == "游戏用户"
    assert merged["scenario"] == "低延迟保障"  # 非空字段不被覆盖


def test_check_profile_missing_all_empty() -> None:
    profile = {"user_profile": {"user_type": "", "scenario": "", "guarantee_period": {}}}
    missing = check_profile_missing(profile)
    assert "user_type" in missing
    assert "scenario" in missing
    assert "guarantee_period" in missing


def test_infer_from_app_history_live() -> None:
    profile = load_profile_template()
    result = infer_from_app_history(profile, ["OBS Studio", "抖音直播伴侣"])
    assert result["user_profile"]["user_type"] == "直播用户"
    assert result["user_profile"]["core_metrics"]["bandwidth_priority"] is True


def test_infer_from_app_history_game() -> None:
    profile = load_profile_template()
    result = infer_from_app_history(profile, ["Steam", "英雄联盟"])
    assert result["user_profile"]["user_type"] == "游戏用户"
    assert result["user_profile"]["core_metrics"]["latency_sensitive"] is True
