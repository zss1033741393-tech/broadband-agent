"""工具调用参数自愈单元测试 — 覆盖 core/skill_recovery.py 的 coerce 逻辑。"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.skill_recovery import (
    _coerce_args,
    _coerce_script_path,
    _coerce_timeout,
    skill_script_pre_hook,
)


# ── _coerce_args ─────────────────────────────────────────────────────────────


def test_args_none_passthrough():
    assert _coerce_args(None) is None


def test_args_list_str_passthrough():
    assert _coerce_args(["--flag", "value"]) == ["--flag", "value"]


def test_args_list_with_non_str_elements():
    assert _coerce_args([1, 2]) == ["1", "2"]


def test_args_str_shlex_split():
    assert _coerce_args("--flag value") == ["--flag", "value"]


def test_args_str_single_word():
    assert _coerce_args("singleword") == ["singleword"]


def test_args_str_json_list():
    assert _coerce_args('["-f", "v"]') == ["-f", "v"]


def test_args_dict_to_json_element():
    result = _coerce_args({"table": "day"})
    assert result == [json.dumps({"table": "day"}, ensure_ascii=False)]


def test_args_other_scalar():
    assert _coerce_args(42) == ["42"]


# ── _coerce_script_path ───────────────────────────────────────────────────────


def test_script_path_strips_directory():
    assert _coerce_script_path("scripts/run.py") == "run.py"


def test_script_path_plain_filename():
    assert _coerce_script_path("run.py") == "run.py"


def test_script_path_windows_separator():
    assert _coerce_script_path("scripts\\run.py") == "run.py"


def test_script_path_non_str():
    assert _coerce_script_path(123) == "123"


# ── _coerce_timeout ───────────────────────────────────────────────────────────


def test_timeout_int_passthrough():
    assert _coerce_timeout(30) == 30


def test_timeout_str_to_int():
    assert _coerce_timeout("30") == 30


def test_timeout_invalid_str_fallback():
    assert _coerce_timeout("bad") == 30


def test_timeout_none_fallback():
    assert _coerce_timeout(None) == 30


# ── skill_script_pre_hook ─────────────────────────────────────────────────────


class _FakeFunctionCall:
    """最小 FunctionCall stub，只需 arguments 属性。"""

    def __init__(self, arguments: dict):
        self.arguments = arguments


def test_pre_hook_coerces_dict_args():
    fc = _FakeFunctionCall({"args": {"table": "day"}, "script_path": "run.py"})
    skill_script_pre_hook(fc)
    assert fc.arguments["args"] == [json.dumps({"table": "day"}, ensure_ascii=False)]


def test_pre_hook_coerces_str_args():
    fc = _FakeFunctionCall({"args": "--flag value", "script_path": "run.py"})
    skill_script_pre_hook(fc)
    assert fc.arguments["args"] == ["--flag", "value"]


def test_pre_hook_strips_script_path():
    fc = _FakeFunctionCall({"script_path": "scripts/run.py"})
    skill_script_pre_hook(fc)
    assert fc.arguments["script_path"] == "run.py"


def test_pre_hook_coerces_timeout():
    fc = _FakeFunctionCall({"timeout": "60"})
    skill_script_pre_hook(fc)
    assert fc.arguments["timeout"] == 60


def test_pre_hook_none_arguments_is_noop():
    fc = _FakeFunctionCall.__new__(_FakeFunctionCall)
    fc.arguments = None
    skill_script_pre_hook(fc)  # should not raise
    assert fc.arguments is None
