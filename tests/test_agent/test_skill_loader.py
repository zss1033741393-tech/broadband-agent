"""Skills 发现与工具注册测试

测试新架构下：
  - _discover_skills()：LocalSkills 自动扫描 skills/ 目录
  - _build_agno_tools()：各 Skill 脚本注册为 Agno Function tools
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestDiscoverSkills:
    def test_discover_skills_returns_skills_object(self) -> None:
        """_discover_skills 应返回 Agno Skills 实例"""
        from agno.skills import Skills
        from app.agent.agent import _discover_skills
        skills = _discover_skills()
        assert isinstance(skills, Skills)

    def test_skills_contains_all_skill_dirs(self) -> None:
        """Skills 应包含所有含 SKILL.md 的子目录"""
        from app.agent.agent import _discover_skills
        skills = _discover_skills()
        names = skills.get_skill_names()
        for expected in ["intent_parser", "user_profiler", "plan_generator",
                         "constraint_checker", "config_translator", "domain_expert"]:
            assert expected in names, f"Skill '{expected}' 未被发现"

    def test_skills_have_descriptions(self) -> None:
        """每个 Skill 应有非空 description"""
        from app.agent.agent import _discover_skills
        skills = _discover_skills()
        all_skills = skills.get_all_skills()
        # get_all_skills() returns list or dict depending on version
        skill_list = all_skills.values() if isinstance(all_skills, dict) else all_skills
        for skill in skill_list:
            assert skill.description, f"Skill '{skill.name}' 缺少 description"

    def test_skills_provide_meta_tools(self) -> None:
        """Skills 应提供 get_skill_instructions 等元工具"""
        from agno.tools.function import Function
        from app.agent.agent import _discover_skills
        skills = _discover_skills()
        tools = skills.get_tools()
        tool_names = {t.name for t in tools}
        assert "get_skill_instructions" in tool_names
        assert "get_skill_reference" in tool_names
        assert "get_skill_script" in tool_names


class TestBuildAgnoTools:
    def test_build_agno_tools_returns_functions(self) -> None:
        """_build_agno_tools 应为每个 Skill 返回 Agno Function 对象"""
        from agno.tools.function import Function
        from app.agent.agent import _build_agno_tools
        tools = _build_agno_tools()
        assert len(tools) > 0, "应至少注册一个 Agno tool"
        for t in tools:
            assert isinstance(t, Function), f"{t} 不是 Agno Function"

    def test_tool_names_match_expected(self) -> None:
        """注册的 tool 名称应在预期集合中"""
        from app.agent.agent import _build_agno_tools
        tools = _build_agno_tools()
        tool_names = {t.name for t in tools}
        expected = {"intent_parsing", "user_profile", "plan_filling", "constraint_check", "config_translation"}
        assert tool_names <= expected, f"多余的 tool 名称: {tool_names - expected}"

    def test_intent_parsing_tool_callable(self) -> None:
        """intent_parsing tool 应能正常调用并返回合法 JSON"""
        from app.agent.agent import _build_agno_tools
        tools = _build_agno_tools()
        ip_tool = next((t for t in tools if t.name == "intent_parsing"), None)
        assert ip_tool is not None, "未找到 intent_parsing tool"
        result = ip_tool.entrypoint(intent_goal_json="{}")
        data = json.loads(result)
        assert "complete" in data
        assert "missing_fields" in data
        assert "schema" in data

    def test_constraint_check_tool_callable(self) -> None:
        """constraint_check tool 应能正常调用并返回合法 JSON"""
        from app.agent.agent import _build_agno_tools
        tools = _build_agno_tools()
        cc_tool = next((t for t in tools if t.name == "constraint_check"), None)
        assert cc_tool is not None, "未找到 constraint_check tool"
        plans = {"cei_perception": {"trigger_window": {"start": "07:00", "end": "11:00"}}}
        result = cc_tool.entrypoint(plans_json=json.dumps(plans))
        data = json.loads(result)
        assert "passed" in data
        assert "violations" in data
