"""冒烟测试 — 覆盖新架构 (Team + 10 Skills) 的导入、配置与脚本执行。"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# 确保项目根目录在 path
_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ============================================================================
# 配置 & 目录结构
# ============================================================================


def test_config_files_exist():
    """配置文件存在。"""
    root = Path(_ROOT)
    assert (root / "configs" / "model.yaml").exists()
    assert (root / "configs" / "agents.yaml").exists()
    assert (root / "configs" / "downstream.yaml").exists()


def test_model_config_loads():
    from core.model_loader import load_model_config
    cfg = load_model_config()
    assert "provider" in cfg
    assert "model" in cfg


def test_agents_config_structure():
    """agents.yaml 结构正确：team + 5 个 agents。"""
    import yaml
    cfg_path = Path(_ROOT) / "configs" / "agents.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    assert "team" in cfg
    assert cfg["team"]["mode"] == "coordinate"
    assert cfg["team"]["prompt"] == "prompts/orchestrator.md"

    agents = cfg.get("agents", {})
    expected_agents = {
        "planning",
        "insight",
        "provisioning_wifi",
        "provisioning_delivery",
        "provisioning_cei_chain",
    }
    assert expected_agents.issubset(agents.keys())

    # Planning 挂载 3 个 Skill
    assert set(agents["planning"]["skills"]) == {"goal_parsing", "plan_design", "plan_review"}
    # CEI 链实例挂载 3 个 Skill
    assert set(agents["provisioning_cei_chain"]["skills"]) == {
        "cei_pipeline",
        "fault_diagnosis",
        "remote_optimization",
    }
    # WIFI 实例只挂 wifi_simulation
    assert agents["provisioning_wifi"]["skills"] == ["wifi_simulation"]
    # Delivery 实例只挂 differentiated_delivery
    assert agents["provisioning_delivery"]["skills"] == ["differentiated_delivery"]


def test_all_skills_present():
    """10 个 Skill 目录均存在且含 SKILL.md。"""
    skills_dir = Path(_ROOT) / "skills"
    expected_skills = [
        "goal_parsing",
        "plan_design",
        "plan_review",
        "cei_pipeline",
        "fault_diagnosis",
        "remote_optimization",
        "differentiated_delivery",
        "wifi_simulation",
        "data_insight",
        "report_rendering",
    ]
    for name in expected_skills:
        skill_path = skills_dir / name
        assert skill_path.exists(), f"Skill 目录缺失: {name}"
        assert (skill_path / "SKILL.md").exists(), f"SKILL.md 缺失: {name}"


def test_all_prompts_present():
    """4 份 prompt 作业手册均存在且非空。"""
    prompts_dir = Path(_ROOT) / "prompts"
    for name in ("orchestrator.md", "planning.md", "insight.md", "provisioning.md"):
        p = prompts_dir / name
        assert p.exists(), f"Prompt 缺失: {name}"
        assert len(p.read_text(encoding="utf-8")) > 200, f"Prompt 太短: {name}"


def test_old_artifacts_removed():
    """旧架构的文件已清理（避免代码引用旧路径）。"""
    root = Path(_ROOT)
    assert not (root / "configs" / "agent.yaml").exists()
    assert not (root / "prompts" / "main_agent_system.md").exists()
    for old_skill in (
        "slot_filling",
        "solution_generation",
        "solution_verification",
        "cei_config",
        "fault_config",
        "remote_loop",
        "report_generation",
    ):
        assert not (root / "skills" / old_skill).exists(), f"旧 skill 未清理: {old_skill}"


# ============================================================================
# Skill 脚本执行（参数 schema 驱动）
# ============================================================================


def _load_script(skill_name: str, script_name: str):
    """从 skill 目录动态加载脚本模块，返回模块对象。"""
    path = Path(_ROOT) / "skills" / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"{skill_name}_{script_name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_goal_parsing_slot_engine():
    mod = _load_script("goal_parsing", "slot_engine.py")
    result = json.loads(mod.process("", "{}"))
    assert "state" in result
    assert result["is_complete"] is False
    assert len(result["missing_slots"]) > 0

    result2 = json.loads(mod.process("直播套餐卖场走播用户，18:00-22:00 保障抖音直播", "{}"))
    state = result2["state"]
    assert state.get("package_type") == "直播套餐"
    assert state.get("scenario") == "卖场走播"
    assert "18:00-22:00" in (state.get("time_window") or "")
    assert state.get("guarantee_app") == "抖音"


def test_plan_review_checker():
    mod = _load_script("plan_review", "checker.py")
    result = json.loads(mod.review("## WIFI 仿真方案\n**启用**: true"))
    assert "passed" in result
    assert "violations" in result
    assert "recommendations" in result
    assert "checks" in result
    assert len(result["checks"]) == 4


def test_cei_pipeline_render():
    mod = _load_script("cei_pipeline", "render.py")
    result = json.loads(
        mod.render(
            json.dumps(
                {
                    "threshold": 70,
                    "granularity": "minute",
                    "model": "live_streaming",
                    "time_window": "18:00-22:00",
                    "target_pon": "全部",
                }
            )
        )
    )
    assert result["skill"] == "cei_pipeline"
    assert result["params"]["threshold"] == 70
    assert "yaml_config" in result
    assert "cei_spark" in result["yaml_config"]
    assert "dispatch_result" in result


def test_cei_pipeline_invalid_enum_falls_back():
    mod = _load_script("cei_pipeline", "render.py")
    # 非法 model 回退为默认值 general
    result = json.loads(mod.render(json.dumps({"model": "bogus", "threshold": 65})))
    assert result["params"]["model"] == "general"
    assert result["params"]["threshold"] == 65


def test_fault_diagnosis_render():
    mod = _load_script("fault_diagnosis", "render.py")
    result = json.loads(
        mod.render(
            json.dumps(
                {
                    "fault_tree_enabled": True,
                    "whitelist_rules": ["偶发卡顿"],
                    "severity_threshold": "warning",
                }
            )
        )
    )
    assert result["skill"] == "fault_diagnosis"
    assert result["params"]["fault_tree_enabled"] is True
    assert "偶发卡顿" in result["config_json"]
    assert "dispatch_result" in result


def test_remote_optimization_skill_schema():
    """SKILL.md 声明了新的 strategy / rectification_method / operation_time schema。"""
    skill_md = (
        Path(_ROOT) / "skills" / "remote_optimization" / "SKILL.md"
    ).read_text(encoding="utf-8")
    for keyword in (
        "strategy",
        "rectification_method",
        "operation_time",
        "immediate",
        "scheduled",
        "idle",
        "fae_poc",
    ):
        assert keyword in skill_md, f"SKILL.md 缺少关键字: {keyword}"
    # 旧 schema 关键字应已被清理
    for stale in ("trigger_mode", "coverage_weak_enabled"):
        assert stale not in skill_md, f"SKILL.md 残留旧 schema: {stale}"


def test_remote_optimization_normalize_params():
    """manual_batch_optimize 的参数归一化正确处理各种输入。"""
    mod = _load_script("remote_optimization", "manual_batch_optimize.py")

    # JSON list
    normalized = mod._normalize_params(
        {"strategy": "idle", "rectification_method": [1, 2]}
    )
    assert normalized["strategy"] == "idle"
    assert normalized["rectification_method"] == [1, 2]

    # 逗号分隔字符串
    normalized = mod._normalize_params(
        {"strategy": "scheduled", "rectification_method": "1,3,4", "operation_time": "0-0-3-*-*-*"}
    )
    assert normalized["rectification_method"] == [1, 3, 4]
    assert normalized["operation_time"] == "0-0-3-*-*-*"

    # 空值 → None（代表全部）
    normalized = mod._normalize_params({"strategy": "immediate"})
    assert normalized["rectification_method"] is None


def test_remote_optimization_invalid_params_rejected():
    """非法 strategy / rectification_method 应被拒绝。"""
    mod = _load_script("remote_optimization", "manual_batch_optimize.py")
    import pytest as _pytest

    with _pytest.raises(ValueError, match="strategy"):
        mod._normalize_params({"strategy": "bogus"})

    with _pytest.raises(ValueError, match="rectification_method"):
        mod._normalize_params({"strategy": "idle", "rectification_method": [5]})


def test_remote_optimization_cli_args_builder():
    """_build_cli_args 生成与 argparse 兼容的参数序列。"""
    mod = _load_script("remote_optimization", "manual_batch_optimize.py")

    cli = mod._build_cli_args(
        {
            "strategy": "scheduled",
            "rectification_method": [1, 2, 3],
            "operation_time": "0-0-0-*-*-*",
            "config": None,
        }
    )
    assert cli[:2] == ["--strategy", "scheduled"]
    assert "--rectification-method" in cli
    assert "1,2,3" in cli
    assert "--operation-time" in cli
    assert "0-0-0-*-*-*" in cli

    # strategy != scheduled 时不带 --operation-time
    cli = mod._build_cli_args(
        {
            "strategy": "idle",
            "rectification_method": None,
            "operation_time": "0-0-0-*-*-*",
            "config": None,
        }
    )
    assert "--operation-time" not in cli
    assert "--rectification-method" not in cli


def test_remote_optimization_execute_graceful_failure():
    """未部署 NCELogin.py / config.ini 时,execute() 返回结构化失败而非抛异常。"""
    mod = _load_script("remote_optimization", "manual_batch_optimize.py")
    result = mod.execute(
        {
            "strategy": "idle",
            "rectification_method": [1, 2],
            "operation_time": "0-0-0-*-*-*",
            "config": None,
        }
    )
    assert result["skill"] == "remote_optimization"
    assert "params" in result
    assert "dispatch_result" in result
    # 当前 CI 环境未部署 fae_poc/config.ini 或 fae_poc/NCELogin.py,
    # 应返回 status=failed + stage=deployment_check 或 ncelogin_import
    assert result["dispatch_result"]["status"] == "failed"
    assert result["dispatch_result"]["stage"] in {
        "deployment_check",
        "ncelogin_import",
    }


def test_remote_optimization_dual_syspath_injection():
    """脚本顶部 prelude 同时注入项目根 + fae_poc 目录到 sys.path。

    这保证 `from fae_poc import ...` 和 `from NCELogin import NCELogin`
    两种导入风格都能工作。
    """
    # 加载脚本 (触发其顶部的 sys.path 注入)
    _load_script("remote_optimization", "manual_batch_optimize.py")
    assert _ROOT in sys.path, "项目根未注入 sys.path"
    fae_poc_dir = str(Path(_ROOT) / "fae_poc")
    assert fae_poc_dir in sys.path, "fae_poc/ 目录未注入 sys.path"


def test_remote_optimization_bare_ncelogin_import_works():
    """验证 bare 导入 `from NCELogin import NCELogin` 的路径在 CI 环境也可工作。

    做法: 临时在 fae_poc/ 下放一个 stub NCELogin.py,触发导入,然后清理。
    测试结束后不能残留 stub,也不能污染 sys.modules。
    """
    _load_script("remote_optimization", "manual_batch_optimize.py")

    fae_poc_dir = Path(_ROOT) / "fae_poc"
    stub_path = fae_poc_dir / "NCELogin.py"
    stub_existed = stub_path.exists()
    backup = stub_path.read_text(encoding="utf-8") if stub_existed else None

    try:
        if not stub_existed:
            stub_path.write_text(
                "class NCELogin:\n"
                "    def __init__(self, config_file=None):\n"
                "        self.config_file = config_file\n",
                encoding="utf-8",
            )
        # 确保缓存被清理后重新导入
        sys.modules.pop("NCELogin", None)
        import NCELogin as _bare  # type: ignore  # noqa: F401
        assert hasattr(_bare, "NCELogin")
        instance = _bare.NCELogin(config_file="/tmp/fake.ini")
        assert instance.config_file == "/tmp/fake.ini"
    finally:
        sys.modules.pop("NCELogin", None)
        if not stub_existed and stub_path.exists():
            stub_path.unlink()
        elif stub_existed and backup is not None:
            stub_path.write_text(backup, encoding="utf-8")


def test_fae_poc_package_importable():
    """fae_poc 包可 import,即使 NCELogin.py / config.ini 未部署。"""
    import importlib
    # 确保项目根在 sys.path
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    fae_poc = importlib.import_module("fae_poc")
    assert hasattr(fae_poc, "DEFAULT_CONFIG_PATH")
    assert hasattr(fae_poc, "EXAMPLE_CONFIG_PATH")
    assert hasattr(fae_poc, "require_config")
    assert hasattr(fae_poc, "require_ncelogin")
    # 未部署时 require_* 应抛出带引导信息的错误
    import pytest as _pytest
    with _pytest.raises(FileNotFoundError, match="config.ini"):
        fae_poc.require_config()
    # NCELogin.py 未提交时应优雅提示
    if fae_poc.NCELogin is None:
        with _pytest.raises(RuntimeError, match="NCELogin"):
            fae_poc.require_ncelogin()


def test_fae_poc_example_committed():
    """config.ini.example 模板必须提交,真实 config.ini 不得提交。"""
    fae_poc_dir = Path(_ROOT) / "fae_poc"
    assert (fae_poc_dir / "__init__.py").exists()
    assert (fae_poc_dir / "config.ini.example").exists()
    # 真实文件不应出现在 git 跟踪的检查点 — 本测试不强行断言其不存在
    # （开发者可能已在本地部署），仅确保 .gitignore 规则存在
    gitignore = (Path(_ROOT) / ".gitignore").read_text(encoding="utf-8")
    assert "fae_poc/config.ini" in gitignore
    assert "fae_poc/NCELogin.py" in gitignore


def test_differentiated_delivery_render():
    mod = _load_script("differentiated_delivery", "render.py")
    result = json.loads(
        mod.render(
            json.dumps(
                {
                    "slice_type": "application_slice",
                    "target_app": "抖音",
                    "whitelist": ["douyin.com"],
                    "bandwidth_guarantee_mbps": 50,
                }
            )
        )
    )
    assert result["skill"] == "differentiated_delivery"
    assert result["params"]["target_app"] == "抖音"
    assert "抖音" in result["config_json"]
    assert "slice_id" in result["dispatch_result"]


def test_data_insight_query_stage():
    mod = _load_script("data_insight", "mock_query.py")
    result = json.loads(mod.query("query"))
    assert result["skill"] == "data_insight"
    assert result["stage"] == "query"
    assert "data" in result
    assert "echarts_option" in result
    assert result["echarts_option"]["series"][0]["type"] == "bar"
    assert "summary" in result
    assert "priority_pons" in result["summary"]


def test_data_insight_attribution_stage():
    mod = _load_script("data_insight", "mock_query.py")
    result = json.loads(mod.query("attribution"))
    assert result["stage"] == "attribution"
    assert "analysis" in result
    assert result["echarts_option"]["series"][0]["type"] == "radar"


def test_wifi_simulation_four_steps():
    mod = _load_script("wifi_simulation", "simulate.py")
    result = json.loads(mod.simulate("{}"))
    assert result["skill"] == "wifi_simulation"
    assert len(result["steps"]) == 4
    step_names = [s["name"] for s in result["steps"]]
    assert step_names == [
        "户型图识别",
        "热力图生成",
        "RSSI 采集",
        "选点对比",
    ]
    for step in result["steps"]:
        assert "echarts_option" in step
        assert step["status"] == "success"


def test_report_rendering():
    mod = _load_script("report_rendering", "render_report.py")
    ctx = json.dumps(
        {
            "title": "测试报告",
            "summary": {
                "priority_pons": ["PON-2/0/5"],
                "distinct_issues": ["带宽利用率过高"],
                "scope_indicator": "regional",
            },
            "analysis": [
                {
                    "pon_port": "PON-2/0/5",
                    "cei_score": 48.9,
                    "issues": ["带宽利用率过高"],
                    "probable_causes": ["用户数过多"],
                    "recommendation": "建议优先关注",
                }
            ],
        }
    )
    md = mod.render(ctx)
    assert "测试报告" in md
    assert "PON-2/0/5" in md
    assert "带宽利用率过高" in md


# ============================================================================
# Agno Team 装配
# ============================================================================


def test_localskills_loads_all():
    """LocalSkills 能扫描并加载 10 个 Skill。"""
    from agno.skills.loaders.local import LocalSkills
    loader = LocalSkills(str(Path(_ROOT) / "skills"), validate=False)
    skills = loader.load()
    assert len(skills) == 10
    names = {s.name for s in skills}
    assert "goal_parsing" in names
    assert "plan_design" in names
    assert "cei_pipeline" in names
    assert "differentiated_delivery" in names


def test_create_team_structure():
    """create_team() 产出 1 leader + 5 member 的 Team。"""
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

    from agno.team import Team
    from agno.team.team import TeamMode
    from core.agent_factory import create_team

    team = create_team(session_id="smoke-test-session")
    assert isinstance(team, Team)
    assert team.mode == TeamMode.coordinate
    assert len(team.members) == 5

    member_names = [m.name for m in team.members]
    assert set(member_names) == {
        "planning",
        "insight",
        "provisioning_wifi",
        "provisioning_delivery",
        "provisioning_cei_chain",
    }

    # 每个 member 的 skills 子集正确
    for m in team.members:
        skill_names = {s.name for s in m.skills.get_all_skills()} if m.skills else set()
        if m.name == "planning":
            assert skill_names == {"goal_parsing", "plan_design", "plan_review"}
        elif m.name == "insight":
            assert skill_names == {"data_insight", "report_rendering"}
        elif m.name == "provisioning_wifi":
            assert skill_names == {"wifi_simulation"}
        elif m.name == "provisioning_delivery":
            assert skill_names == {"differentiated_delivery"}
        elif m.name == "provisioning_cei_chain":
            assert skill_names == {"cei_pipeline", "fault_diagnosis", "remote_optimization"}


# ============================================================================
# 可观测性
# ============================================================================


def test_db_init():
    from core.observability.db import Database
    import tempfile
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        d = Database(db_path)
        sid = d.create_session("test-hash")
        assert sid is not None
        assert d.get_session_id("test-hash") == sid
        d.insert_message(sid, "user", "hello")
        d.insert_trace(sid, "test-hash", "request", {"input": "hello"})
        d.end_session("test-hash", "test")
    finally:
        db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
