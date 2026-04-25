# 优化计划：工具调用参数错误自愈（方向 1）

> 目标：当 LLM 传给 agno 工具的参数类型不对时，框架不再返回无用的 Pydantic
> 原始报错，而是返回**结构化错误 + 修正指导**，使 LLM 能在下一轮直接改对。

## 0. 问题精确定位

| 层级 | 文件 (agno 源码) | 行号 | 现状 |
|------|------------------|------|------|
| ① validate_call 包装 | `tools/function.py` `_wrap_callable()` | 608 | 裸 `validate_call(func)` — 参数类型不匹配直接抛 `ValidationError` |
| ② 异常捕获 | `tools/function.py` `FunctionCall.execute()` | 1092-1096 | 通用 `except Exception`，`self.error = str(e)` — 原始 Pydantic 文本 |
| ③ 错误消息回传 | `models/base.py` `create_function_call_result()` | 2088 | `content = function_call.error` — 把原始文本当作 tool_result |
| ④ 重试循环 | `models/base.py` `aresponse_stream()` | 1840 | `continue` 循环存在 — LLM 确实能看到错误 |

**断裂点**：④ 的循环虽存在，但 ②③ 传回的错误信息对 LLM 无效（无修正指导），
导致 LLM 高概率重复相同错误直至 tool_call_limit 耗尽。

## 1. 改造架构（3 层）

```
Layer 1: 智能验证包装 — Function._wrap_callable()
  ↓ 拦截 ValidationError，尝试类型自动修正
  ↓ 修正成功 → 直接调用原函数（无需重试）
  ↓ 修正失败 → 进入 Layer 2

Layer 2: 增强错误构建 — 新增 agno/tools/_validation_recovery.py
  ↓ 从 ValidationError 提取结构化信息
  ↓ 结合函数签名、参数 schema 生成 LLM 可读的修正指导
  ↓ 返回增强错误（不是 raise）

Layer 3: Skill 工具特化 — Skills._get_skill_script() 签名放宽
  ↓ args: Optional[List[str]] → args: Any
  ↓ 内部做类型诊断 + 修正 + 引导
  ↓ 类似 OpenCode 的 get_skill_script.ts 风格
```

## 2. Layer 1：智能验证包装

**文件**：`agno/tools/function.py` — `Function._wrap_callable()` (line 561)

**当前代码**（line 608）：
```python
wrapped = validate_call(func, config=dict(arbitrary_types_allowed=True))
```

**改为**：
```python
validated_func = validate_call(func, config=dict(arbitrary_types_allowed=True))

@functools.wraps(func)
def _smart_validated(*args, **kwargs):
    try:
        return validated_func(*args, **kwargs)
    except ValidationError as ve:
        # Phase A: 尝试自动修正
        coerced_kwargs = _try_coerce_args(func, kwargs, ve)
        if coerced_kwargs is not None:
            try:
                return validated_func(*args, **coerced_kwargs)
            except Exception:
                pass  # 修正失败，进入 Phase B
        # Phase B: 生成增强错误信息
        from agno.tools._validation_recovery import build_recovery_message
        return build_recovery_message(func, ve, kwargs)

wrapped = _smart_validated
```

**类型修正规则** `_try_coerce_args()`：

| LLM 常见错误 | 期望类型 | 实际传值 | 修正策略 |
|---|---|---|---|
| `args="--flag value"` | `List[str]` | `str` | `shlex.split(value)` |
| `args={"k":"v"}` | `List[str]` | `dict` | `[json.dumps(value)]` |
| `timeout="30"` | `int` | `str` | `int(value)` |
| `execute="true"` | `bool` | `str` | 已由 `clean_arguments` 处理 |
| `args=None` | `Optional[List[str]]` | `NoneType` | 合法，不需修正 |

**关键约束**：
- `_smart_validated` **不改变原函数签名**，JSON Schema 不受影响
- 自动修正仅针对 Pydantic `ValidationError`，其它异常原路抛出
- 修正成功时**静默执行**，不打断 LLM 对话；修正失败时返回引导字符串
- `build_recovery_message()` 返回的是 **普通字符串**（不是异常），
  FunctionCall.execute() 按正常结果处理 → `FunctionExecutionResult(status="success")`
  → LLM 看到的是一条"友好的工具输出"而非 `tool_call_error=True` 的系统错误

## 3. Layer 2：增强错误构建

**新增文件**：`agno/tools/_validation_recovery.py`

```python
"""Pydantic ValidationError → LLM 可读修正指导。"""

import json
from inspect import signature
from typing import Any, Callable, get_type_hints

from pydantic import ValidationError


def build_recovery_message(func: Callable, error: ValidationError, kwargs: dict[str, Any]) -> str:
    """把 ValidationError 转化为 LLM 一次就能改对的引导消息。"""

    sig = signature(func)
    hints = get_type_hints(func)

    lines = ["⚠️ Tool call parameter error — please fix and retry:\n"]

    for err in error.errors():
        loc = err.get("loc", ())
        field = str(loc[-1]) if loc else "unknown"
        expected = _friendly_type(hints.get(field))
        actual_val = kwargs.get(field)
        actual_type = type(actual_val).__name__

        lines.append(f"  ✗ `{field}`: expected {expected}, got {actual_type} = {_truncate(actual_val)}")
        lines.append(f"    → {err.get('msg', '')}")

    # 正确调用签名
    lines.append("\nCorrect calling convention:")
    params = []
    for name, param in sig.parameters.items():
        if name in ("self", "agent", "team", "run_context"):
            continue
        hint = _friendly_type(hints.get(name))
        default = f" = {param.default!r}" if param.default is not param.empty else ""
        params.append(f"  {name}: {hint}{default}")
    lines.append("\n".join(params))

    # 特殊：如果是 skill 工具，附带可用资源
    if hasattr(func, "__self__") and hasattr(func.__self__, "get_skill_names"):
        skills_obj = func.__self__
        lines.append(f"\nAvailable skills: {', '.join(skills_obj.get_skill_names())}")
        if "skill_name" in kwargs:
            skill = skills_obj.get_skill(kwargs["skill_name"])
            if skill and skill.scripts:
                lines.append(f"Available scripts for '{kwargs['skill_name']}': {skill.scripts}")

    lines.append("\nIMPORTANT: `args` must be a List[str], e.g. args=[\"--flag\", \"value\"]")

    return "\n".join(lines)


def _friendly_type(hint: Any) -> str:
    """类型注解 → 人类可读字符串。"""
    if hint is None:
        return "Any"
    origin = getattr(hint, "__origin__", None)
    if origin is not None:
        args = getattr(hint, "__args__", ())
        args_str = ", ".join(_friendly_type(a) for a in args)
        return f"{getattr(origin, '__name__', str(origin))}[{args_str}]"
    return getattr(hint, "__name__", str(hint))


def _truncate(val: Any, max_len: int = 80) -> str:
    s = repr(val)
    return s if len(s) <= max_len else s[:max_len] + "..."
```

## 4. Layer 3：Skill 工具签名放宽

**文件**：`agno/skills/agent_skills.py` — `_get_skill_script()` (line 272)

**当前签名**：
```python
def _get_skill_script(self, skill_name: str, script_path: str,
                      execute: bool = False,
                      args: Optional[List[str]] = None,
                      timeout: int = 30) -> str:
```

**改为**：
```python
def _get_skill_script(self, skill_name: str, script_path: str,
                      execute: bool = False,
                      args: Any = None,
                      timeout: Any = 30) -> str:
```

**函数体头部增加修正逻辑**：
```python
# ── 参数修正（对齐 OpenCode get_skill_script.ts） ──
# timeout 修正
if isinstance(timeout, str):
    try:
        timeout = int(timeout)
    except ValueError:
        timeout = 30

# args 修正
if args is not None:
    if isinstance(args, str):
        # LLM 经常传字符串而非列表
        import shlex
        try:
            args = shlex.split(args)
        except ValueError:
            args = [args]
    elif isinstance(args, dict):
        # LLM 传 dict 而非 list — 序列化为单元素列表
        args = [json.dumps(args, ensure_ascii=False)]
    elif not isinstance(args, list):
        args = [str(args)]
    # 确保列表中每个元素都是字符串
    args = [str(a) for a in args]

# script_path 修正（对齐 OpenCode 的 scriptName.split("/").pop()）
if "/" in script_path:
    script_path = script_path.split("/")[-1]
```

## 5. 实施步骤

### Step 1：新增 `_validation_recovery.py`
- 路径：`agno/tools/_validation_recovery.py`
- 内容：上面 Layer 2 的完整代码
- 职责：ValidationError → LLM 友好消息

### Step 2：修改 `Function._wrap_callable()` — Layer 1
- 路径：`agno/tools/function.py` line 561-610
- 改动：替换裸 `validate_call` 为 `_smart_validated` 包装
- 新增：`_try_coerce_args()` 内联函数

### Step 3：修改 `Skills._get_skill_script()` — Layer 3
- 路径：`agno/skills/agent_skills.py` line 272-290
- 改动：放宽 `args`/`timeout` 类型 + 头部修正逻辑
- 效果：大多数参数错误在这一层就被自动修正，Layer 1/2 作为兜底

### Step 4：回归测试
```bash
uv run pytest tests/test_smoke.py -v
```
加新增单元测试覆盖以下场景：
- `args="--flag value"` → 自动 split 为 `["--flag", "value"]`
- `args={"table": "day"}` → 自动转为 `['{"table": "day"}']`
- `timeout="30"` → 自动转为 `30`
- `script_path="scripts/run.py"` → 自动修正为 `"run.py"`
- 修正失败时返回 LLM 可读的引导消息（含正确签名 + 可用脚本列表）

### Step 5：移除 Prompt 里的"铁律"硬约束
框架层自愈后，`prompts/provisioning.md` 和 `prompts/insight.md` 中
关于 `args` 必须为 `List[str]` 的"铁律"可以**软化为建议**而非强制。
减少 prompt token 开销，让 LLM 更自然地调用工具。

## 6. 效果对比

| 维度 | 当前 (agno 原生) | 优化后 | OpenCode |
|------|-------------------|--------|----------|
| args 类型错误 | Pydantic 报错文本 → LLM 困惑 | 自动修正 / 引导消息 | 自动修正 / `return "Error: ..."` |
| 重试次数 | 2-3 次（常失败） | 0 次（自动修正）或 1 次（引导后） | 0-1 次 |
| prompt token 开销 | 铁律占 ~200 token/agent | 可删除铁律 | 无需铁律 |
| 影响范围 | 仅 Skill 工具 | 所有 agno 工具（通用 Layer 1/2）+ Skill 特化（Layer 3） | 仅自定义工具 |
| 对 agno 侵入性 | 无 | 中等（3 处改动 + 1 新文件） | N/A（独立框架） |

## 7. 文件变更清单

| 文件 | 改动 | 类型 |
|------|------|------|
| `agno/tools/_validation_recovery.py` | **新增** | Layer 2 增强错误构建 |
| `agno/tools/function.py` | 修改 `_wrap_callable()` | Layer 1 智能验证 |
| `agno/skills/agent_skills.py` | 修改 `_get_skill_script()` 签名 + 修正逻辑 | Layer 3 Skill 特化 |
| `tests/test_tool_error_recovery.py` | **新增** | 回归测试 |
| `prompts/provisioning.md` | 软化铁律 | prompt 优化 |
| `prompts/insight.md` | 软化铁律 | prompt 优化 |
