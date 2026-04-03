"""
JSON 模板文件完整性测试

运行：pytest tests/test_templates/test_json_templates.py -v
"""

import json
import os

import pytest

TEMPLATE_DIR = "templates"
REQUIRED_TEMPLATES = [
    "user_profile",
    "cei_perception_plan",
    "fault_diagnosis_plan",
    "remote_closure_plan",
    "dynamic_optimization_plan",
    "manual_fallback_plan",
]


class TestTemplateFiles:
    def test_all_required_templates_exist(self):
        """所有必需模板文件存在"""
        for name in REQUIRED_TEMPLATES:
            path = os.path.join(TEMPLATE_DIR, f"{name}.json")
            assert os.path.exists(path), f"模板文件缺失: {path}"

    def test_all_templates_valid_json(self):
        """所有模板文件是合法的 JSON"""
        for name in REQUIRED_TEMPLATES:
            path = os.path.join(TEMPLATE_DIR, f"{name}.json")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{name}.json 根节点应为 dict"

    def test_cei_perception_plan_structure(self):
        """CEI 方案模板结构校验"""
        with open(os.path.join(TEMPLATE_DIR, "cei_perception_plan.json")) as f:
            data = json.load(f)
        plan = data["cei_perception_plan"]
        assert "warning_threshold" in plan
        assert "perception_granularity" in plan
        assert "trigger_window" in plan
        assert "latency_ms" in plan["warning_threshold"]

    def test_remote_closure_plan_structure(self):
        """远程闭环方案模板结构校验"""
        with open(os.path.join(TEMPLATE_DIR, "remote_closure_plan.json")) as f:
            data = json.load(f)
        plan = data["remote_closure_plan"]
        assert "closure_options" in plan
        assert "closure_strategy" in plan
        assert "audit_strategy" in plan
