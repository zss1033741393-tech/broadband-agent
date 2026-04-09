#!/usr/bin/env python3
"""FAE 平台手动批量优化接口调用入口。

支持两种调用方式（由 Provisioning Agent 使用 JSON 入口，命令行调试使用 argparse 入口）:

1. JSON 入口（单个位置参数）::

       python manual_batch_optimize.py '{"strategy": "idle", "rectification_method": [1,2]}'

2. 标准 argparse CLI 入口::

       python manual_batch_optimize.py --strategy idle --rectification-method 1,2
       python manual_batch_optimize.py --strategy scheduled --operation-time 0-0-0-*-*-*

两种入口最终都会汇聚到 `execute()`，调用 `fae_poc.NCELogin` 下发接口，
并把结果以 JSON 形式写到 stdout（供 Skill 上层透传）。

部署要求：
- `fae_poc/NCELogin.py` 必须存在（用户本地部署）
- `fae_poc/config.ini` 必须存在（可通过 `--config` 显式指定）
详见 `fae_poc/README.md`。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─── fae_poc 包注入 ────────────────────────────────────────────────────
# 从 skills/<skill>/scripts/<file> 向上 3 级定位项目根，使 `fae_poc` 可被导入
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fae_poc import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    require_config,
    require_ncelogin,
)


# ─── 参数 schema ───────────────────────────────────────────────────────
_ALLOWED_STRATEGIES = {"immediate", "idle", "scheduled"}
_ALLOWED_METHODS = {1, 2, 3, 4}
_DEFAULT_OPERATION_TIME = "0-0-0-*-*-*"


def _normalize_rectification_method(
    raw: Any,
) -> Optional[List[int]]:
    """归一化整改方式字段。

    接受的输入格式：
      - None / [] / ""          → 返回 None (代表"全部")
      - [1, 2, 3]               → 保留为 list[int]
      - "1,2,3"                 → 解析为 list[int]
      - 1                       → 包装成 [1]

    Returns:
        归一化后的 list[int]，或 None 表示不指定该参数
    """
    if raw is None or raw == "" or raw == []:
        return None
    if isinstance(raw, int):
        raw = [raw]
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.split(",") if x.strip()]
    if not isinstance(raw, list):
        raise ValueError(f"rectification_method 类型非法: {type(raw).__name__}")
    parsed: List[int] = []
    for item in raw:
        try:
            value = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"rectification_method 元素无法转 int: {item!r}") from exc
        if value not in _ALLOWED_METHODS:
            raise ValueError(
                f"rectification_method 元素 {value} 不在允许集合 {sorted(_ALLOWED_METHODS)}"
            )
        parsed.append(value)
    return parsed or None


def _normalize_params(raw: Dict[str, Any]) -> Dict[str, Any]:
    """把外部传入的 dict 校验 + 补默认值，产出标准化参数。"""
    strategy = raw.get("strategy", "immediate") or "immediate"
    if strategy not in _ALLOWED_STRATEGIES:
        raise ValueError(
            f"strategy 非法: {strategy!r}, 允许值: {sorted(_ALLOWED_STRATEGIES)}"
        )
    rectification_method = _normalize_rectification_method(
        raw.get("rectification_method")
    )
    operation_time = raw.get("operation_time") or _DEFAULT_OPERATION_TIME
    config_path = raw.get("config")

    return {
        "strategy": strategy,
        "rectification_method": rectification_method,
        "operation_time": operation_time,
        "config": str(config_path) if config_path else None,
    }


def _build_cli_args(params: Dict[str, Any]) -> List[str]:
    """根据标准化参数组装一份与 argparse 兼容的 CLI 参数序列。

    便于调试日志与 stdout 里回显"实际触发的命令行等价形式"。
    """
    cli: List[str] = ["--strategy", params["strategy"]]
    if params.get("rectification_method"):
        cli += [
            "--rectification-method",
            ",".join(str(x) for x in params["rectification_method"]),
        ]
    if params["strategy"] == "scheduled":
        cli += ["--operation-time", params["operation_time"]]
    if params.get("config"):
        cli += ["--config", params["config"]]
    return cli


# ─── 真实接口调用 ──────────────────────────────────────────────────────
def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """执行一次批量优化调用。

    Args:
        params: 已标准化的参数 dict (来自 _normalize_params)

    Returns:
        完整的 stdout JSON 结构。**本函数不抛异常** — 任何部署缺失、
        参数非法、接口报错都会以 `dispatch_result.status=failed` 的形式返回，
        保证 Skill 上层总能获得一个结构化 JSON 透传给用户。
    """
    result: Dict[str, Any] = {
        "skill": "remote_optimization",
        "params": dict(params),
        "cli_args": _build_cli_args(params),
    }

    try:
        config_path = require_config(
            Path(params["config"]) if params.get("config") else DEFAULT_CONFIG_PATH
        )
        NCELoginCls = require_ncelogin()
    except (FileNotFoundError, RuntimeError) as exc:
        result["dispatch_result"] = {
            "status": "failed",
            "stage": "deployment_check",
            "message": str(exc),
            "task_id": None,
        }
        return result

    # 至此 config.ini 与 NCELogin 均已就绪，回写解析后的 config 绝对路径
    result["params"]["config"] = str(config_path)
    result["cli_args"] = _build_cli_args(result["params"])

    try:
        # TODO(用户): 按 NCELogin 的实际 API 调整以下调用
        # ──────────────────────────────────────────────────────────
        # 下面是一个占位样板，请替换为真实接口。典型流程：
        #   client = NCELoginCls(config_path)
        #   response = client.manual_batch_optimize(
        #       strategy=params["strategy"],
        #       rectification_method=params["rectification_method"],
        #       operation_time=params["operation_time"].replace("-", " "),
        #   )
        #   result["dispatch_result"] = {
        #       "status": "success" if response.ok else "failed",
        #       "message": response.get("message", ""),
        #       "task_id": response.get("taskId"),
        #       "raw": response,
        #   }
        client = NCELoginCls(str(config_path))  # noqa: F841  [placeholder]
        result["dispatch_result"] = {
            "status": "success",
            "stage": "placeholder",
            "message": "manual_batch_optimize 调用占位：请在 execute() 中接入真实 NCELogin API",
            "task_id": None,
        }
    except Exception as exc:
        result["dispatch_result"] = {
            "status": "failed",
            "stage": "api_call",
            "message": f"{type(exc).__name__}: {exc}",
            "task_id": None,
        }

    return result


# ─── 入口解析 ──────────────────────────────────────────────────────────
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """标准 argparse CLI 入口（用于命令行调试）。"""
    parser = argparse.ArgumentParser(
        description="手动批量优化接口调用工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "使用示例:\n"
            "  python manual_batch_optimize.py --strategy immediate\n"
            "  python manual_batch_optimize.py --strategy idle --rectification-method 1,2,3\n"
            "  python manual_batch_optimize.py --strategy scheduled --operation-time 0-0-0-*-*-*\n"
            "  python manual_batch_optimize.py --config /abs/path/to/fae_poc/config.ini\n"
            "\n"
            "参数连接符统一为空格（argparse 标准），不要使用带冒号的形式。\n"
            "operation-time 使用 `-` 分隔的 6 段 cron 表达式，程序内部会转换为空格。"
        ),
    )
    parser.add_argument(
        "--strategy",
        "-s",
        default="immediate",
        choices=sorted(_ALLOWED_STRATEGIES),
        help="执行策略：immediate(默认)/idle/scheduled",
    )
    parser.add_argument(
        "--rectification-method",
        "-r",
        default=None,
        help="整改方式列表，逗号分隔，如 1,2,3,4；不传代表全部",
    )
    parser.add_argument(
        "--operation-time",
        "-o",
        default=_DEFAULT_OPERATION_TIME,
        help=f"cron 表达式（仅 strategy=scheduled 生效），默认 {_DEFAULT_OPERATION_TIME}",
    )
    parser.add_argument(
        "--config",
        "-c",
        default=None,
        help=f"config.ini 绝对路径，留空使用默认 {DEFAULT_CONFIG_PATH}",
    )
    return parser.parse_args(argv)


def _try_parse_json_entry(argv: List[str]) -> Optional[Dict[str, Any]]:
    """检测是否是"单参数 JSON"入口形式。

    Provisioning Agent 统一传一个 JSON 字符串作为唯一位置参数时，这里识别并解析。
    """
    if len(argv) != 1:
        return None
    candidate = argv[0].strip()
    if not (candidate.startswith("{") and candidate.endswith("}")):
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # 双入口：JSON 单参数 OR 标准 argparse
    json_params = _try_parse_json_entry(argv)
    try:
        if json_params is not None:
            normalized = _normalize_params(json_params)
        else:
            ns = parse_args(argv)
            normalized = _normalize_params(
                {
                    "strategy": ns.strategy,
                    "rectification_method": ns.rectification_method,
                    "operation_time": ns.operation_time,
                    "config": ns.config,
                }
            )
    except ValueError as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "skill": "remote_optimization",
                    "error": "invalid_params",
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.stdout.write("\n")
        return 2

    result = execute(normalized)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    sys.stdout.write("\n")
    return 0 if result.get("dispatch_result", {}).get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
