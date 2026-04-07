"""OutputSink — 阶段产出物持久化

落盘有两条路径（互为冗余）：
  1. 直接工具落盘（主路径）：analyze_intent / generate_plans / check_constraints /
     translate_configs 内部调用 _persist_stage() 直接写文件
  2. Hook 兜底（遗留路径）：output_sink_hook 拦截 get_skill_script 调用，
     从 stdout JSON 提取结果写文件。仅当 Agent 绕过直接工具走 Skill 脚本时触发

session_id 管理：
  - UI 层在对话开始时通过 set_current_session_id() 设置
  - Hook 从 Agno RunContext 同步更新

输出结构：
  outputs/{session_id}/
    ├── intent.json       ← analyze_intent
    ├── plans.json        ← generate_plans
    ├── constraint.json   ← check_constraints
    └── configs.json      ← translate_configs
"""
from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger("outputs.sink")

# 脚本文件名 → 阶段名映射
_SCRIPT_TO_STAGE: dict[str, str] = {
    "analyze.py": "intent",
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


def set_current_session_id(session_id: str) -> None:
    """显式设置当前会话 ID（由 UI 层在对话开始时调用）。"""
    global _current_session_id
    _current_session_id = session_id


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


async def output_sink_hook(
    name: str,
    func: Callable,
    args: dict,
    run_context: Any = None,
) -> Any:
    """tool_hook：拦截 get_skill_script 调用，保存阶段产出物。

    Agno 按 hook 签名自动注入参数：
      name         — 工具函数名
      func         — next_func（调用后继续执行链，async 上下文中为协程函数）
      args         — 工具入参 dict
      run_context  — Agno RunContext，含 session_id / run_id
    """
    result = func(**args)
    # Agno async 执行链中 next_func 返回 coroutine，必须 await
    if inspect.isawaitable(result):
        result = await result

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
