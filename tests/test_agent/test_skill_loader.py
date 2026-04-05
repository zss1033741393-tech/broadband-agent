"""Skills 发现与脚本 CLI 入口测试

新架构下：
  - discover_skills(): LocalSkills 原生扫描，每个技能目录独立注册
  - Skills 自动提供 get_skill_instructions / get_skill_script 元工具
  - 每个脚本有 CLI 入口，可被 get_skill_script(execute=True) 调用
  - 不存在 _build_agno_tools() 或手写工具包装器
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


class TestDiscoverSkills:

    def test_discover_skills_returns_skills_object(self) -> None:
        from agno.skills import Skills
        from app.agent.agent import discover_skills, SKILLS_DIR
        assert isinstance(discover_skills(SKILLS_DIR), Skills)

    def test_discovers_all_six_skills(self) -> None:
        from app.agent.agent import discover_skills, SKILLS_DIR
        skills = discover_skills(SKILLS_DIR)
        names = skills.get_skill_names()
        for expected in ["intent_profiler", "plan_generator",
                         "constraint_checker", "config_translator", "domain_expert"]:
            assert expected in names, f"Skill '{expected}' 未被发现"

    def test_all_skills_have_descriptions(self) -> None:
        from app.agent.agent import discover_skills, SKILLS_DIR
        skills = discover_skills(SKILLS_DIR)
        all_skills = skills.get_all_skills()
        skill_list = all_skills.values() if isinstance(all_skills, dict) else all_skills
        for skill in skill_list:
            assert skill.description, f"Skill '{skill.name}' 缺少 description"

    def test_meta_tools_registered(self) -> None:
        """Skills 应自动注入 3 个元工具，不需要手写工具包装"""
        from app.agent.agent import discover_skills, SKILLS_DIR
        tools = discover_skills(SKILLS_DIR).get_tools()
        tool_names = {t.name for t in tools}
        assert tool_names == {"get_skill_instructions", "get_skill_reference", "get_skill_script"}

    def test_no_manual_tool_builders(self) -> None:
        """agent.py 不应存在 _build_agno_tools — 技能通过元工具原生执行"""
        import app.agent.agent as m
        assert not hasattr(m, "_build_agno_tools")
        assert not hasattr(m, "_import_script")

    def test_executable_scripts_discovered(self) -> None:
        """每个有 scripts/ 目录的 Skill 应至少有一个脚本被发现"""
        from app.agent.agent import discover_skills, SKILLS_DIR
        skills = discover_skills(SKILLS_DIR)
        all_skills = skills.get_all_skills()
        skill_list = all_skills.values() if isinstance(all_skills, dict) else all_skills
        skills_with_scripts = [s for s in skill_list if s.name != "domain_expert"]
        for skill in skills_with_scripts:
            assert skill.scripts, f"Skill '{skill.name}' 应有脚本文件"


class TestScriptCLIEntryPoints:
    """验证每个脚本有 CLI 入口，可被 subprocess 执行"""

    def _run_script(self, script_path: Path, *args) -> dict:
        result = subprocess.run(
            [sys.executable, str(script_path)] + list(args),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"脚本 {script_path.name} 返回码非零: {result.stderr}"
        return json.loads(result.stdout)

    def test_analyze_cli_empty_intent(self) -> None:
        """analyze.py CLI：空意图应返回 complete=false"""
        data = self._run_script(SKILLS_DIR / "intent_profiler/scripts/analyze.py", "{}")
        assert "complete" in data
        assert "missing_fields" in data
        assert "intent_goal" in data
        assert "profile" in data
        assert "schema" in data
        assert data["complete"] is False

    def test_analyze_cli_complete_intent(self) -> None:
        """analyze.py CLI：完整意图应返回 complete=true"""
        intent = {"user_type": "直播用户", "scenario": "上行带宽保障",
                  "guarantee_target": {"priority_level": "high"}}
        data = self._run_script(
            SKILLS_DIR / "intent_profiler/scripts/analyze.py",
            json.dumps(intent)
        )
        assert data["complete"] is True

    def test_generate_cli(self) -> None:
        """generate.py CLI：应返回 5 个方案填充结果"""
        intent = {
            "user_type": "直播用户",
            "guarantee_target": {"sensitivity": "卡顿", "priority_level": "high"},
            "guarantee_period": {"start_time": "20:00", "end_time": "23:00"},
        }
        data = self._run_script(
            SKILLS_DIR / "plan_generator/scripts/generate.py",
            json.dumps(intent)
        )
        assert "plans" in data
        assert len(data["plans"]) == 5

    def test_validate_cli(self) -> None:
        """validate.py CLI：应返回校验结果"""
        plans = {}
        intent = {"guarantee_period": {"start_time": "20:00", "end_time": "23:00"}}
        data = self._run_script(
            SKILLS_DIR / "constraint_checker/scripts/validate.py",
            json.dumps(plans),
            json.dumps(intent),
        )
        assert "passed" in data

    def test_translate_cli(self) -> None:
        """translate.py CLI：应返回配置转译结果"""
        plans = {}
        data = self._run_script(
            SKILLS_DIR / "config_translator/scripts/translate.py",
            json.dumps(plans),
        )
        assert "configs" in data
        assert "schema" in data
