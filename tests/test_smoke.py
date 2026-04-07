"""冒烟测试 — 覆盖核心模块可导入、配置可加载、Skills 可解析。"""

import json
import sys
from pathlib import Path

# 确保项目根目录在 path
_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_config_files_exist():
    """配置文件存在。"""
    root = Path(_ROOT)
    assert (root / "configs" / "model.yaml").exists()
    assert (root / "configs" / "agent.yaml").exists()
    assert (root / "configs" / "downstream.yaml").exists()
    assert (root / "configs" / "slot_schema.yaml").exists()


def test_model_config_loads():
    """model.yaml 可正常解析。"""
    from core.model_loader import load_model_config
    cfg = load_model_config()
    assert "provider" in cfg
    assert "model" in cfg


def test_agent_config_loads():
    """agent.yaml 可正常解析。"""
    import yaml
    cfg_path = Path(_ROOT) / "configs" / "agent.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    assert cfg["name"] == "home-broadband-agent"
    assert "enabled_skills" in cfg


def test_slot_schema_loads():
    """slot_schema.yaml 可正常解析。"""
    import yaml
    schema_path = Path(_ROOT) / "configs" / "slot_schema.yaml"
    with open(schema_path) as f:
        schema = yaml.safe_load(f)
    assert schema["root"] == "user_type"
    assert "slots" in schema
    assert "user_type" in schema["slots"]


def test_slot_engine():
    """slot_engine 可正常运行。"""
    sys.path.insert(0, str(Path(_ROOT) / "skills" / "slot_filling" / "scripts"))
    from slot_engine import process

    # 空状态
    result = json.loads(process("{}", ""))
    assert "state" in result
    assert "is_complete" in result
    assert result["is_complete"] is False
    assert len(result["missing_slots"]) > 0

    # 带输入
    result2 = json.loads(process("{}", "直播套餐卖场走播用户，18:00-22:00"))
    state = result2["state"]
    assert state.get("package_type") == "直播套餐"
    assert state.get("scenario") == "卖场走播"
    assert "18:00-22:00" in state.get("time_window", "")


def test_solution_render():
    """方案模板可正常渲染。"""
    sys.path.insert(0, str(Path(_ROOT) / "skills" / "solution_generation" / "scripts"))
    from render import render_all

    profile = json.dumps({
        "user_type": "主播用户",
        "package_type": "直播套餐",
        "scenario": "卖场走播",
        "guarantee_target": "STA级",
        "time_window": "18:00-22:00",
    })
    result = json.loads(render_all(profile))
    assert "cei_config" in result
    assert "fault_config" in result
    assert "remote_loop" in result
    assert "wifi_simulation" in result


def test_mock_query():
    """mock 数据查询可正常运行。"""
    sys.path.insert(0, str(Path(_ROOT) / "skills" / "data_insight" / "scripts"))
    from mock_query import query

    result = json.loads(query("all"))
    assert "data" in result
    assert "analysis" in result
    assert "summary" in result
    assert len(result["data"]) > 0


def test_mock_checker():
    """mock 约束校验可正常运行。"""
    sys.path.insert(0, str(Path(_ROOT) / "skills" / "solution_verification" / "scripts"))
    from checker import check

    result = json.loads(check("{}"))
    assert "passed" in result
    assert "checks" in result


def test_db_init():
    """SQLite 数据库可正常初始化。"""
    from core.observability.db import Database
    import tempfile
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        d = Database(db_path)
        sid = d.create_session("test-hash")
        assert sid is not None
        assert d.get_session_id("test-hash") == sid
        d.insert_message(sid, "user", "hello")
        d.insert_trace(sid, "request", {"input": "hello"})
        d.end_session("test-hash", "test")
    finally:
        db_path.unlink(missing_ok=True)


def test_skills_directory_structure():
    """所有 Skill 目录结构正确（有 SKILL.md）。"""
    skills_dir = Path(_ROOT) / "skills"
    expected_skills = [
        "cei_config", "wifi_simulation", "fault_config", "remote_loop",
        "slot_filling", "solution_generation", "solution_verification",
        "data_insight", "report_generation",
    ]
    for skill_name in expected_skills:
        skill_path = skills_dir / skill_name
        assert skill_path.exists(), f"Skill 目录不存在: {skill_name}"
        assert (skill_path / "SKILL.md").exists(), f"SKILL.md 缺失: {skill_name}"


def test_system_prompt_exists():
    """System prompt 文件存在且非空。"""
    prompt_path = Path(_ROOT) / "prompts" / "main_agent_system.md"
    assert prompt_path.exists()
    content = prompt_path.read_text()
    assert len(content) > 100


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
