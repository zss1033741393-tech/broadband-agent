"""agno Skills 子类：在 validate_call 之前用 pre_hook 自动修正 get_skill_script 的参数类型。

设计原理：
  agno FunctionCall.execute() 顺序：
    _handle_pre_hook()  ← fc.arguments 在这里被修正
    ↓
    entrypoint(**self.arguments)  ← validate_call 在这里运行（看到已修正的参数）

  因此 pre_hook 能完全避免 ValidationError，使 LLM 无需重试。
"""

import json
import shlex
from typing import Any, Optional

from agno.skills import Skills
from agno.tools.function import Function, FunctionCall


def _coerce_args(val: Any) -> Optional[list[str]]:
    """把 LLM 常见的错误 args 格式统一修正为 List[str]。"""
    if val is None:
        return None
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        stripped = val.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except Exception:
                pass
        try:
            return shlex.split(stripped)
        except ValueError:
            return [stripped]
    if isinstance(val, dict):
        return [json.dumps(val, ensure_ascii=False)]
    return [str(val)]


def _coerce_script_path(val: Any) -> str:
    """去除路径前缀，只保留文件名（对齐 OpenCode scriptName.split('/').pop()）。"""
    if not isinstance(val, str):
        return str(val)
    return val.split("/")[-1].split("\\")[-1]


def _coerce_timeout(val: Any) -> int:
    """把字符串 timeout 修正为 int，失败时回退到默认值 30。"""
    if isinstance(val, int):
        return val
    try:
        return int(val)
    except (ValueError, TypeError):
        return 30


def skill_script_pre_hook(fc: FunctionCall) -> None:
    """get_skill_script 的参数修正 hook，在 validate_call 之前执行。"""
    if fc.arguments is None:
        return
    if "args" in fc.arguments:
        fc.arguments["args"] = _coerce_args(fc.arguments["args"])
    if "script_path" in fc.arguments:
        fc.arguments["script_path"] = _coerce_script_path(fc.arguments["script_path"])
    if "timeout" in fc.arguments:
        fc.arguments["timeout"] = _coerce_timeout(fc.arguments["timeout"])


class RobustSkills(Skills):
    """Skills 子类：自动为 get_skill_script 注入参数修正 pre_hook。

    不修改 agno 源码，通过 agno 提供的 pre_hook 扩展点在项目层面实现自愈。
    """

    def get_tools(self) -> list[Function]:
        tools = super().get_tools()
        for tool in tools:
            if tool.name == "get_skill_script":
                tool.pre_hook = skill_script_pre_hook
        return tools
