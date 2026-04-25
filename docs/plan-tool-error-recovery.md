# 优化计划：工具调用参数错误自愈（项目层方案）

> 目标：当 LLM 传给 `get_skill_script` 的参数类型不对时（如 `args={"table":"day"}` 或
> `args="--flag value"`），框架自动修正参数而非返回无用的 Pydantic 报错，使调用直接成功。

## 约束

**不修改 agno 源码**（agno 作为 PyPI 依赖安装于 site-packages）。  
利用 agno 已有的 `pre_hook` 扩展点在项目层面实现自愈。

## 问题根因

```
agno FunctionCall.execute() 顺序：
  _handle_pre_hook()         ← agno 提供的扩展点
  ↓
  entrypoint(**self.arguments)  ← validate_call 包装，类型不匹配抛 ValidationError
```

`ValidationError` 虽然会被 `except Exception` 捕获并作为 `tool_result` 返回给 LLM，
但原始 Pydantic 报错文本对 LLM 无效，导致 LLM 高概率重复相同错误直至 `tool_call_limit` 耗尽。

## 解决方案

利用 `pre_hook` 在 `validate_call` 之前修正参数，彻底消除 `ValidationError`。

### 新增文件：`core/skill_recovery.py`

```
_coerce_args()        — str/dict/list/None → Optional[List[str]]
_coerce_script_path() — "scripts/run.py" → "run.py"（去目录前缀）
_coerce_timeout()     — "30" → 30（str → int，失败回退 30）
skill_script_pre_hook() — FunctionCall pre_hook，修正 arguments 后 validate_call 就通过
RobustSkills(Skills)  — 覆写 get_tools()，为 get_skill_script 注入 pre_hook
```

### 修改：`core/agent_factory.py`

```python
from core.skill_recovery import RobustSkills
# _build_subset_skills() 末尾：
return RobustSkills(loaders=[_StaticLoader(selected)])  # 原为 Skills(...)
```

## 修正规则

| LLM 常见错误 | 期望类型 | 修正策略 |
|---|---|---|
| `args="--flag value"` | `List[str]` | `shlex.split()` |
| `args='["-f","v"]'` | `List[str]` | `json.loads()` → list |
| `args={"table":"day"}` | `List[str]` | `[json.dumps(dict)]` |
| `args=["a","b"]` | `List[str]` | `[str(x) for x in list]`（直接通过） |
| `args=None` | `Optional[List[str]]` | 保持 None |
| `script_path="scripts/run.py"` | `str`（文件名） | `"run.py"` |
| `timeout="30"` | `int` | `int("30")` → 30 |

## 文件变更

| 文件 | 类型 |
|------|------|
| `core/skill_recovery.py` | **新增** |
| `core/agent_factory.py` | 修改（1 import + 1 行） |
