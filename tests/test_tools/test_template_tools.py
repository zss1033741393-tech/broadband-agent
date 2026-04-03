"""
template_tools 单元测试

运行：pytest tests/test_tools/test_template_tools.py -v
"""

import pytest

from app.tools.template_tools import _deep_merge, fill_template, load_template, set_nested_value


class TestLoadTemplate:
    def test_load_existing_template(self):
        template = load_template("cei_perception_plan")
        assert "cei_perception_plan" in template
        assert "warning_threshold" in template["cei_perception_plan"]

    def test_load_nonexistent_template(self):
        template = load_template("nonexistent_plan")
        assert template == {}

    def test_all_templates_loadable(self):
        names = [
            "user_profile",
            "cei_perception_plan",
            "fault_diagnosis_plan",
            "remote_closure_plan",
            "dynamic_optimization_plan",
            "manual_fallback_plan",
        ]
        for name in names:
            t = load_template(name)
            assert isinstance(t, dict), f"{name} 加载失败"


class TestFillTemplate:
    def test_simple_fill(self):
        template = {"cei_perception_plan": {"warning_threshold": {"latency_ms": 100}}}
        params = {"cei_perception_plan": {"warning_threshold": {"latency_ms": 50}}}
        result = fill_template(template, params)
        assert result["cei_perception_plan"]["warning_threshold"]["latency_ms"] == 50

    def test_fill_does_not_mutate_original(self):
        template = {"a": {"b": 1}}
        original_value = template["a"]["b"]
        fill_template(template, {"a": {"b": 2}})
        assert template["a"]["b"] == original_value  # 原始模板未被修改

    def test_deep_merge_adds_new_keys(self):
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        _deep_merge(base, override)
        assert base["a"]["x"] == 1
        assert base["a"]["y"] == 2


class TestSetNestedValue:
    def test_set_existing_path(self):
        data = {"a": {"b": {"c": 1}}}
        set_nested_value(data, "a.b.c", 99)
        assert data["a"]["b"]["c"] == 99

    def test_set_creates_missing_keys(self):
        data = {}
        set_nested_value(data, "a.b.c", 42)
        assert data["a"]["b"]["c"] == 42
