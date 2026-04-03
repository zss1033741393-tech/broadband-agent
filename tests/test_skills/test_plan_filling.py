"""方案填充 Skill 单元测试"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.plan_filling.scripts.filler import (
    build_params_from_intent,
    fill_all_templates,
    fill_template,
    load_template,
)


def test_load_template() -> None:
    template = load_template("cei_perception.json")
    assert "cei_perception" in template
    assert template["cei_perception"]["warning_threshold"]["latency_ms"] == 100


def test_fill_template_changes_params() -> None:
    template = load_template("cei_perception.json")
    params = {"cei_perception.warning_threshold.latency_ms": 50}
    filled, changes = fill_template(template, params)
    assert filled["cei_perception"]["warning_threshold"]["latency_ms"] == 50
    assert len(changes) == 1


def test_build_params_live_user() -> None:
    intent = {
        "user_type": "直播用户",
        "guarantee_target": {"sensitivity": "卡顿", "priority_level": "high"},
        "guarantee_period": {"start_time": "19:00", "end_time": "23:00"},
    }
    params = build_params_from_intent(intent, "cei_perception.json")
    assert params.get("cei_perception.warning_threshold.latency_ms") == 50
    assert params.get("cei_perception.perception_granularity.per_user_enabled") is True


def test_fill_all_templates_async() -> None:
    intent = {
        "user_type": "游戏用户",
        "guarantee_target": {"sensitivity": "延迟", "priority_level": "high"},
        "guarantee_period": {"start_time": "21:00", "end_time": "00:00"},
    }
    results = asyncio.run(fill_all_templates(intent))
    assert len(results) == 5
    assert all(r["status"] == "filled" for r in results)
