"""OutputSink — 阶段产出物持久化

通过 Agno tool_hooks 机制拦截 get_skill_script 的执行结果，
将四个阶段产出物按 session_id 分目录写入 outputs/。

设计原则：
  - Skills 脚本保持纯 stdout，完全不感知 session 或文件路径
  - session_id 由 Agno 框架通过 run_context 注入，不经过 Skills 层
  - hook 纯观测，原样返回结果，不影响 Agent 任何逻辑

输出结构：
  outputs/
  └── {session_id}/
      ├── intent.json       ← intent_parser/scripts/extract.py
      ├── profile.json      ← user_profiler/scripts/query_profile.py
      ├── plans.json        ← plan_generator/scripts/generate.py
      ├── constraint.json   ← constraint_checker/scripts/validate.py
      └── configs.json      ← config_translator/scripts/translate.py
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("outputs.sink")

# 脚本文件名 → 阶段名映射
_SCRIPT_TO_STAGE: dict[str, str] = {
    "extract.py": "intent",
    "query_profile.py": "profile",
    "generate.py": "plans",
    "validate.py": "constraint",
    "translate.py": "configs",
}

_OUTPUTS_ROOT = Path("outputs")

# 当前活跃会话 ID（由 output_sink_hook 在首次工具调用时更新）
_current_session_id: str | None = None


def get_current_session_id() -> str | None:
    """返回当前活跃会话 ID，供 get_pipeline_file 工具读取。"""
    return _current_session_id


def _resolve_session_dir(session_id: str | None) -> Path:
    sid = session_id or "unknown"
    session_dir = _OUTPUTS_ROOT / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _extract_stdout_json(result: Any) -> dict | None:
    """从 get_skill_script 返回值中提取 stdout JSON。

    Agno get_skill_script 返回格式为字符串，内容类似：
      {"stdout": "{...}", "stderr": "", "returncode": 0}
    或直接是脚本 stdout 的字符串。
    """
    try:
        if isinstance(result, str):
            outer = json.loads(result)
            # 标准格式：外层含 stdout 字段
            if isinstance(outer, dict) and "stdout" in outer:
                return json.loads(outer["stdout"])
            # 降级：result 本身就是 JSON
            return outer
        if isinstance(result, dict):
            if "stdout" in result:
                return json.loads(result["stdout"])
            return result
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return None


def output_sink_hook(
    name: str,
    func: Callable,
    args: dict,
    run_context: Any = None,
) -> Any:
    """tool_hook：拦截 get_skill_script 调用，保存阶段产出物。

    Agno 按 hook 签名自动注入参数：
      name         — 工具函数名
      func         — next_func（调用后继续执行链）
      args         — 工具入参 dict
      run_context  — Agno RunContext，含 session_id / run_id
    """
    result = func(**args)

    # 只处理 get_skill_script 且 execute=True 的调用
    if name != "get_skill_script" or not args.get("execute", False):
        return result

    script_path = args.get("script_path", "") or args.get("script", "")
    script_name = Path(script_path).name
    stage = _SCRIPT_TO_STAGE.get(script_name)

    if not stage:
        return result

    session_id = getattr(run_context, "session_id", None) if run_context else None
    if session_id:
        global _current_session_id
        _current_session_id = session_id
    session_dir = _resolve_session_dir(session_id)
    output_file = session_dir / f"{stage}.json"

    payload = _extract_stdout_json(result)
    if payload is None:
        logger.warning("OutputSink: 无法解析 %s 的 stdout JSON，跳过写入", script_name)
        return result

    try:
        output_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("OutputSink: %s → %s", stage, output_file)
    except OSError as exc:
        logger.warning("OutputSink: 写入失败 %s: %s", output_file, exc)

    return result
