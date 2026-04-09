#!/usr/bin/env python3
"""远程优化配置渲染 — 参数 schema 驱动。

作为 agno Skill 脚本被调用。不做业务规则判断。
"""

import json
import random
import sys
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "references"

_SCHEMA_DEFAULTS: Dict[str, Any] = {
    "trigger_mode": "idle",
    "action": "config_push",
    "time_window": "全天",
    "coverage_weak_enabled": False,
}

_ALLOWED_MODES = {"immediate", "idle", "scheduled"}
_ALLOWED_ACTIONS = {"gateway_restart", "config_push", "coverage_tune", "speed_test"}


def _validate_and_fill(params: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {**_SCHEMA_DEFAULTS, **params}
    if merged.get("trigger_mode") not in _ALLOWED_MODES:
        merged["trigger_mode"] = _SCHEMA_DEFAULTS["trigger_mode"]
    if merged.get("action") not in _ALLOWED_ACTIONS:
        merged["action"] = _SCHEMA_DEFAULTS["action"]
    if not isinstance(merged.get("coverage_weak_enabled"), bool):
        merged["coverage_weak_enabled"] = bool(merged.get("coverage_weak_enabled", False))
    return merged


def _mock_dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    action = params.get("action", "config_push")
    outcomes_by_action = {
        "gateway_restart": [
            {"status": "success", "message": "网关已成功重启，链路恢复正常", "loop_id": f"LOOP-{random.randint(10000, 99999)}"},
            {"status": "failed", "message": "网关重启超时，设备未响应", "error_code": "E3002"},
        ],
        "config_push": [
            {"status": "success", "message": "远程配置下发成功", "loop_id": f"LOOP-{random.randint(10000, 99999)}"},
        ],
        "coverage_tune": [
            {"status": "success", "message": "覆盖参数调节完成，RSSI 改善 3dBm", "loop_id": f"LOOP-{random.randint(10000, 99999)}"},
        ],
        "speed_test": [
            {"status": "success", "message": "测速完成：下行 95Mbps / 上行 45Mbps", "loop_id": f"LOOP-{random.randint(10000, 99999)}"},
        ],
    }
    return random.choice(outcomes_by_action.get(action, [{"status": "success", "message": "执行完成"}]))


def render(params_json: str = "{}") -> str:
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "参数 JSON 解析失败"}, ensure_ascii=False)

    merged = _validate_and_fill(params)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    try:
        tmpl = env.get_template("remote_loop.json.j2")
        config_json = tmpl.render(**merged)
    except Exception as exc:
        return json.dumps({"error": f"渲染失败: {exc}"}, ensure_ascii=False)

    result = {
        "skill": "remote_optimization",
        "params": merged,
        "config_json": config_json,
        "dispatch_result": _mock_dispatch(merged),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    _params = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(render(_params))
