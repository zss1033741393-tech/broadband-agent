"""Skill 发现与注册测试"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.agent.skill_loader import build_agno_tools, build_skills_summary, discover_skills


def test_discover_skills_finds_all() -> None:
    skills = discover_skills()
    names = [s["name"] for s in skills]
    assert "intent_parsing" in names
    assert "user_profile" in names
    assert "plan_filling" in names
    assert "constraint_check" in names
    assert "config_translation" in names
    assert "domain_knowledge" in names


def test_skill_has_description() -> None:
    skills = discover_skills()
    for skill in skills:
        assert skill["description"], f"Skill {skill['name']} 缺少 description"


def test_build_skills_summary() -> None:
    skills = discover_skills()
    summary = build_skills_summary(skills)
    assert "intent_parsing" in summary
    assert len(summary) > 100


def test_build_agno_tools_returns_functions() -> None:
    """build_agno_tools 应为每个有效 Skill 返回 Agno Function 对象"""
    from agno.tools.function import Function

    skills = discover_skills()
    tools = build_agno_tools(skills)
    assert len(tools) > 0, "应至少注册一个 Agno tool"
    for t in tools:
        assert isinstance(t, Function), f"{t} 不是 Agno Function"


def test_agno_tools_names_match_skills() -> None:
    """每个 Agno tool 的名称应与对应 Skill 名称一致"""
    skills = discover_skills()
    tools = build_agno_tools(skills)
    tool_names = {t.name for t in tools}
    skill_names = {s["name"] for s in skills}
    # 所有 tool 名称必须在 skill 名称集合中
    assert tool_names <= skill_names, f"多余的 tool 名称: {tool_names - skill_names}"


def test_intent_parsing_tool_callable() -> None:
    """intent_parsing tool 应能正常调用并返回合法 JSON"""
    skills = discover_skills()
    tools = build_agno_tools(skills)
    ip_tool = next((t for t in tools if t.name == "intent_parsing"), None)
    assert ip_tool is not None, "未找到 intent_parsing tool"

    result = ip_tool.entrypoint(intent_goal_json="{}")
    data = json.loads(result)
    assert "complete" in data
    assert "missing_fields" in data
    assert "schema" in data


def test_constraint_check_tool_callable() -> None:
    """constraint_check tool 应能正常调用并返回合法 JSON"""
    skills = discover_skills()
    tools = build_agno_tools(skills)
    cc_tool = next((t for t in tools if t.name == "constraint_check"), None)
    assert cc_tool is not None, "未找到 constraint_check tool"

    plans = {"cei_perception": {"trigger_window": {"start": "07:00", "end": "11:00"}}}
    result = cc_tool.entrypoint(plans_json=json.dumps(plans))
    data = json.loads(result)
    assert "passed" in data
    assert "violations" in data
