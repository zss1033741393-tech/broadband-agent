"""Skill 发现与注册测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.agent.skill_loader import build_skills_summary, discover_skills


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
