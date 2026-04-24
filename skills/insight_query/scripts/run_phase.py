#!/usr/bin/env python3
"""Phase 批量执行脚本 — 同一 Phase 内所有标准 Step 合并为单次工具调用。

相比每个 Step 单独调用 run_insight.py（每次 ~60-110s LLM round-trip），
本脚本在同一进程内循环调用 run_insight.run()，N 个 Step 只消耗 1 次 round-trip。

输入（argv[1]）：JSON 字符串，形如
    {
        "phase_id": 1,
        "phase_name": "定位低分PON口",
        "table_level": "day",
        "steps": [
            {
                "step_id": 1,
                "step_name": "找出 CEI_score 最低的 PON 口",
                "insight_type": "OutstandingMin",
                "query_config": {
                    "dimensions": [[]],
                    "breakdown": {"name": "portUuid", "type": "UNORDERED"},
                    "measures": [{"name": "CEI_score", "aggr": "AVG"}]
                }
            },
            ...
        ]
    }

输出（stdout）：JSON 字符串，形如
    {
        "status": "ok",
        "skill": "insight_query",
        "op": "run_phase",
        "phase_id": 1,
        "phase_name": "定位低分PON口",
        "table_level": "day",
        "overall_status": "ok",
        "results": [
            {
                "step_id": 1,
                "step_name": "...",
                "insight_type": "OutstandingMin",
                "status": "ok",
                "significance": 0.73,
                "description": {...},
                "filter_data": [...],
                "has_chart": true,
                "chart_file": "/tmp/xxx.json",
                "found_entities": {"portUuid": ["uuid-a"]},
                "data_shape": [3857, 2]
            },
            ...
        ]
    }

overall_status: 任意一个 step 成功则为 "ok"；全部失败才为 "error"。

chart_file 路径原样保留，event_adapter._emit_phase_render_blocks 负责读取并删除。
"""

import json
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# run_insight 与本文件在同一目录，直接函数调用，不走子进程
sys.path.insert(0, str(Path(__file__).parent))
from run_insight import run as run_single  # noqa: E402


def _safe_parse_json(raw: str) -> dict:
    """带简单修复的 JSON 解析，逻辑与 run_insight._safe_parse_json 保持一致。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    stripped = raw.strip()
    if stripped.startswith("'") and stripped.endswith("'"):
        stripped = stripped[1:-1]
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    try:
        from json_repair import repair_json
        return json.loads(repair_json(raw, return_objects=False))
    except (ImportError, Exception):
        pass
    return json.loads(raw)  # 最终尝试，会抛 JSONDecodeError


def run(payload_json: str) -> str:
    """主入口：解析 Phase payload → 逐 Step 调用 run_single → 聚合结果。"""
    try:
        payload: dict[str, Any] = _safe_parse_json(payload_json)
    except json.JSONDecodeError as exc:
        return _err(f"payload JSON 解析失败: {exc}")

    phase_id = payload.get("phase_id")
    phase_name = payload.get("phase_name", "")
    table_level = payload.get("table_level", "day")
    steps = payload.get("steps", [])

    if not isinstance(steps, list) or not steps:
        return _err("payload 缺少 steps 列表或 steps 为空")

    results: list[dict] = []
    any_ok = False

    for step in steps:
        if not isinstance(step, dict):
            results.append({"step_id": None, "status": "error", "error": "step 不是 dict"})
            continue

        step_id = step.get("step_id")
        step_name = step.get("step_name", "")
        insight_type = step.get("insight_type")
        query_config = step.get("query_config")

        # 构造单步 payload，注入 phase/step 元数据
        single_payload: dict[str, Any] = {
            "insight_type": insight_type,
            "query_config": query_config,
            "table_level": table_level,
            "phase_id": phase_id,
            "phase_name": phase_name,
            "step_id": step_id,
            "step_name": step_name,
        }
        # 透传可选字段
        for k in ("value_columns", "group_column", "data_path"):
            if k in step:
                single_payload[k] = step[k]

        try:
            result_str = run_single(json.dumps(single_payload, ensure_ascii=False))
            result: dict = json.loads(result_str)
        except Exception as exc:
            result = {
                "status": "error",
                "skill": "insight_query",
                "op": "run_insight",
                "error": f"step {step_id} 执行异常: {type(exc).__name__}: {exc}",
            }

        # 补充 step 元数据（run_single 已透传，这里仅作保险）
        result.setdefault("step_id", step_id)
        result.setdefault("step_name", step_name)
        result.setdefault("insight_type", insight_type)
        result.setdefault("phase_id", phase_id)
        result.setdefault("phase_name", phase_name)

        if result.get("status") == "ok":
            any_ok = True

        results.append(result)

    overall_status = "ok" if any_ok else "error"

    output: dict[str, Any] = {
        "status": "ok",
        "skill": "insight_query",
        "op": "run_phase",
        "phase_id": phase_id,
        "phase_name": phase_name,
        "table_level": table_level,
        "overall_status": overall_status,
        "results": results,
    }
    return json.dumps(output, ensure_ascii=False, default=_json_default)


def _err(msg: str) -> str:
    return json.dumps(
        {
            "status": "error",
            "skill": "insight_query",
            "op": "run_phase",
            "error": msg,
        },
        ensure_ascii=False,
    )


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return str(obj)


if __name__ == "__main__":
    _payload = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(run(_payload))
