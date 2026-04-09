#!/usr/bin/env python3
"""CEI Spark 配置渲染 — 参数 schema 驱动，纯模板填空。

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
    "threshold": 70,
    "granularity": "minute",
    "model": "general",
    "time_window": "全天",
    "target_pon": "全部",
}

_ALLOWED: Dict[str, Any] = {
    "granularity": {"minute", "hour"},
    "model": {"live_streaming", "gaming", "general", "vvip"},
}


def _validate_and_fill(params: Dict[str, Any]) -> Dict[str, Any]:
    """填补默认值并做简单枚举校验。非法枚举回退为默认值。"""
    merged: Dict[str, Any] = {**_SCHEMA_DEFAULTS, **params}
    for key, allowed in _ALLOWED.items():
        if merged.get(key) not in allowed:
            merged[key] = _SCHEMA_DEFAULTS[key]
    try:
        merged["threshold"] = int(merged["threshold"])
    except (TypeError, ValueError):
        merged["threshold"] = _SCHEMA_DEFAULTS["threshold"]
    return merged


def _mock_dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """[Mock] 配置下发结果。"""
    outcomes = [
        {
            "status": "success",
            "message": "CEI Spark 配置下发成功",
            "config_id": f"CEI-{random.randint(10000, 99999)}",
            "target": params.get("target_pon", "全部"),
        },
        {
            "status": "partial_success",
            "message": "CEI 配置下发部分成功，2/3 节点已生效",
            "config_id": f"CEI-{random.randint(10000, 99999)}",
        },
    ]
    return random.choice(outcomes)


def render(params_json: str = "{}") -> str:
    """渲染 CEI Spark 配置并返回 JSON 结果。"""
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
        tmpl = env.get_template("cei_spark.yaml.j2")
        yaml_config = tmpl.render(**merged)
    except Exception as exc:
        return json.dumps({"error": f"渲染失败: {exc}"}, ensure_ascii=False)

    result = {
        "skill": "cei_pipeline",
        "params": merged,
        "yaml_config": yaml_config,
        "dispatch_result": _mock_dispatch(merged),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    _params = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(render(_params))
