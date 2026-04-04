"""OutputSink 测试

验证：
  - hook 拦截 get_skill_script，按 session_id 分目录写 JSON
  - 非 get_skill_script 调用原样透传，不写文件
  - execute=False 时不写文件
  - stdout JSON 解析失败时跳过写入，不抛异常
  - session_id 缺失时降级到 unknown/
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.outputs.sink import output_sink_hook


@dataclass
class _FakeRunContext:
    session_id: str
    run_id: str = "run-001"


def _make_next_func(return_value):
    """构造一个返回固定值的 next_func"""
    def next_func(**kwargs):
        return return_value
    return next_func


def _skill_script_result(payload: dict) -> str:
    """模拟 get_skill_script(execute=True) 返回的标准格式"""
    return json.dumps({
        "stdout": json.dumps(payload, ensure_ascii=False),
        "stderr": "",
        "returncode": 0,
    })


class TestOutputSinkHook:

    def test_saves_intent_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctx = _FakeRunContext(session_id="sess-abc")
        payload = {"complete": True, "missing_fields": []}

        output_sink_hook(
            name="get_skill_script",
            func=_make_next_func(_skill_script_result(payload)),
            args={"script_path": "extract.py", "execute": True},
            run_context=ctx,
        )

        out = tmp_path / "outputs" / "sess-abc" / "intent.json"
        assert out.exists()
        assert json.loads(out.read_text())["complete"] is True

    def test_saves_configs_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctx = _FakeRunContext(session_id="sess-xyz")
        payload = {"configs": [{"config_type": "perception"}], "success": True, "failed_fields": []}

        output_sink_hook(
            name="get_skill_script",
            func=_make_next_func(_skill_script_result(payload)),
            args={"script_path": "translate.py", "execute": True},
            run_context=ctx,
        )

        out = tmp_path / "outputs" / "sess-xyz" / "configs.json"
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["success"] is True

    def test_all_stage_scripts_mapped(self, tmp_path, monkeypatch):
        """五个阶段脚本都能正确写入对应文件名"""
        monkeypatch.chdir(tmp_path)
        ctx = _FakeRunContext(session_id="sess-all")
        stage_scripts = {
            "extract.py": "intent",
            "query_profile.py": "profile",
            "generate.py": "plans",
            "validate.py": "constraint",
            "translate.py": "configs",
        }
        for script, stage in stage_scripts.items():
            output_sink_hook(
                name="get_skill_script",
                func=_make_next_func(_skill_script_result({"stage": stage})),
                args={"script_path": script, "execute": True},
                run_context=ctx,
            )
        for stage in stage_scripts.values():
            assert (tmp_path / "outputs" / "sess-all" / f"{stage}.json").exists()

    def test_passthrough_non_skill_script_call(self, tmp_path, monkeypatch):
        """非 get_skill_script 调用不写文件，返回值原样透传"""
        monkeypatch.chdir(tmp_path)
        ctx = _FakeRunContext(session_id="sess-pass")
        sentinel = {"key": "value"}

        result = output_sink_hook(
            name="get_skill_instructions",
            func=_make_next_func(sentinel),
            args={"skill_name": "intent_parser"},
            run_context=ctx,
        )

        assert result is sentinel
        assert not (tmp_path / "outputs").exists()

    def test_execute_false_no_write(self, tmp_path, monkeypatch):
        """execute=False 时不写文件"""
        monkeypatch.chdir(tmp_path)
        ctx = _FakeRunContext(session_id="sess-noexec")

        output_sink_hook(
            name="get_skill_script",
            func=_make_next_func("script content"),
            args={"script_path": "extract.py", "execute": False},
            run_context=ctx,
        )

        assert not (tmp_path / "outputs").exists()

    def test_unknown_script_no_write(self, tmp_path, monkeypatch):
        """未知脚本名不写文件，不抛异常"""
        monkeypatch.chdir(tmp_path)
        ctx = _FakeRunContext(session_id="sess-unk")

        output_sink_hook(
            name="get_skill_script",
            func=_make_next_func(_skill_script_result({"x": 1})),
            args={"script_path": "unknown_script.py", "execute": True},
            run_context=ctx,
        )

        assert not (tmp_path / "outputs").exists()

    def test_invalid_json_no_exception(self, tmp_path, monkeypatch):
        """stdout JSON 解析失败时跳过写入，不抛异常"""
        monkeypatch.chdir(tmp_path)
        ctx = _FakeRunContext(session_id="sess-bad")

        output_sink_hook(
            name="get_skill_script",
            func=_make_next_func("not valid json at all"),
            args={"script_path": "extract.py", "execute": True},
            run_context=ctx,
        )

        assert not (tmp_path / "outputs" / "sess-bad" / "intent.json").exists()

    def test_no_run_context_falls_back_to_unknown(self, tmp_path, monkeypatch):
        """run_context 缺失时降级到 outputs/unknown/"""
        monkeypatch.chdir(tmp_path)
        payload = {"complete": False}

        output_sink_hook(
            name="get_skill_script",
            func=_make_next_func(_skill_script_result(payload)),
            args={"script_path": "extract.py", "execute": True},
            run_context=None,
        )

        assert (tmp_path / "outputs" / "unknown" / "intent.json").exists()

    def test_returns_original_result_unchanged(self, tmp_path, monkeypatch):
        """hook 必须原样返回 result，不能修改"""
        monkeypatch.chdir(tmp_path)
        ctx = _FakeRunContext(session_id="sess-ret")
        original = _skill_script_result({"complete": True})

        result = output_sink_hook(
            name="get_skill_script",
            func=_make_next_func(original),
            args={"script_path": "extract.py", "execute": True},
            run_context=ctx,
        )

        assert result == original

    def test_overwrites_on_retry(self, tmp_path, monkeypatch):
        """同一 session 重复执行同一阶段（如约束校验重试）覆盖写入"""
        monkeypatch.chdir(tmp_path)
        ctx = _FakeRunContext(session_id="sess-retry")

        output_sink_hook(
            name="get_skill_script",
            func=_make_next_func(_skill_script_result({"passed": False, "attempt": 1})),
            args={"script_path": "validate.py", "execute": True},
            run_context=ctx,
        )
        output_sink_hook(
            name="get_skill_script",
            func=_make_next_func(_skill_script_result({"passed": True, "attempt": 2})),
            args={"script_path": "validate.py", "execute": True},
            run_context=ctx,
        )

        data = json.loads((tmp_path / "outputs" / "sess-retry" / "constraint.json").read_text())
        assert data["passed"] is True
        assert data["attempt"] == 2
