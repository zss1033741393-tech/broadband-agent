# OpenCode Backend Bridge (路径 A1) — 详细设计方案

> 版本: v1.0 | 日期: 2026-04-25
> 范围: 在现有 FastAPI 后端新增 OpenCode 桥接层，复用已有前端 SSE 协议，实现 agno / OpenCode 双引擎切换

---

## 1. 顶层架构

### 1.1 当前架构（agno 单通道）

```
┌──────────────┐       POST /api/conversations/:id/messages
│   React 前端  │ ─────────────────────────────────────────────► ┌──────────────────┐
│  (SSE 消费)   │ ◄──── SSE: thinking/text/step_start/sub_step  │   FastAPI :8080   │
└──────────────┘       /done/render/error                       │                  │
                                                                │  messages.py     │
                                                                │       ↓          │
                                                                │  agent_bridge.py │
                                                                │       ↓          │
                                                                │  agno Team.arun  │
                                                                │       ↓          │
                                                                │  event_adapter.py│
                                                                └──────────────────┘
```

### 1.2 目标架构（双引擎）

```
┌──────────────┐       POST /api/conversations/:id/messages
│   React 前端  │ ─────────────────────────────────────────────► ┌──────────────────────┐
│  (SSE 消费)   │ ◄──── 完全相同的 SSE 协议                      │   FastAPI :8080       │
│              │                                                │                      │
│  ★ 唯一改动:  │       GET /api/engine                          │  messages.py         │
│  设置页加一个  │ ─────────────────────────────────────────────► │    ├ engine=agno      │
│  引擎切换开关  │                                                │    │   → agent_bridge  │
└──────────────┘                                                │    │   → event_adapter  │
                                                                │    │                    │
                                                                │    └ engine=opencode   │
                                                                │        → oc_bridge ────┼───► opencode serve :4096
                                                                │        → oc_adapter    │         (独立进程)
                                                                └──────────────────────┘
```

**核心原则：前端看到的 SSE 事件协议完全不变，引擎切换对前端透明。**

---

## 2. 后端新增文件清单

```
api/
├── agent_bridge.py          # 不改 — agno 通道保持原样
├── event_adapter.py         # 不改 — agno 事件映射保持原样
├── sse.py                   # 不改 — format_sse 共用
├── opencode_bridge.py       # ★ 新增 — OpenCode Server HTTP 客户端
├── opencode_adapter.py      # ★ 新增 — OpenCode 事件 → 前端 SSE 协议转译
├── engine_config.py         # ★ 新增 — 引擎选择配置
├── routes/
│   ├── messages.py          # ★ 小改 — send_message 路由分发逻辑
│   └── engine.py            # ★ 新增 — GET/PUT /api/engine 配置接口
└── ...
```

---

## 3. 核心模块设计

### 3.1 `engine_config.py` — 引擎选择

```python
"""引擎选择配置。

支持运行时切换 agno / opencode 两个引擎，配置持久化到 data/engine.json。
"""
from pathlib import Path
import json

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "engine.json"
_DEFAULT = {
    "engine": "agno",                       # "agno" | "opencode"
    "opencode_url": "http://127.0.0.1:4096",
    "opencode_agent": "orchestrator",        # 默认使用的 agent
}

def get_config() -> dict:
    if _CONFIG_PATH.exists():
        return {**_DEFAULT, **json.loads(_CONFIG_PATH.read_text())}
    return dict(_DEFAULT)

def set_config(patch: dict) -> dict:
    cfg = get_config()
    cfg.update(patch)
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    return cfg
```

### 3.2 `opencode_bridge.py` — OpenCode Server 客户端

这是 `agent_bridge.py` 的 OpenCode 对等物。职责：管理 conv_id ↔ OpenCode session 映射，发消息，消费事件流。

```python
"""OpenCode Server 与 API 层之间的接缝。

等价于 agent_bridge.py 对 agno 的封装，
但底层调用 OpenCode 的 HTTP API（opencode serve）。
"""
from __future__ import annotations
import httpx
import json
import asyncio
from typing import Any, AsyncGenerator, Optional
from loguru import logger

_log = logger.bind(channel="opencode")

# conv_id → OpenCode session_id 映射（进程内缓存）
_session_map: dict[str, str] = {}


class OpenCodeClient:
    """封装对 opencode serve 的 HTTP 调用。"""

    def __init__(self, base_url: str = "http://127.0.0.1:4096"):
        self.base_url = base_url.rstrip("/")

    async def health(self) -> bool:
        """检查 OpenCode Server 是否在线。"""
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{self.base_url}/global/health")
                return r.status_code == 200
        except Exception:
            return False

    async def ensure_session(self, conv_id: str) -> str:
        """获取或创建 OpenCode session，返回 session_id。"""
        if conv_id in _session_map:
            return _session_map[conv_id]

        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{self.base_url}/session",
                json={"title": f"broadband-{conv_id[:8]}"},
            )
            r.raise_for_status()
            session = r.json()
            sid = session["id"]
            _session_map[conv_id] = sid
            _log.info(f"OpenCode session 创建: conv_id={conv_id} → sid={sid}")
            return sid

    async def send_and_stream(
        self,
        conv_id: str,
        message: str,
        agent: str = "orchestrator",
    ) -> AsyncGenerator[dict, None]:
        """发送消息并消费 SSE 事件流。

        流程：
        1. POST /session/:id/prompt_async 异步发送
        2. GET /event 监听全局 SSE，过滤该 session 的事件
        3. 直到收到 session.idle（该 session 的消息处理完毕）

        Yields:
            OpenCode 原始事件 dict（type + properties）
        """
        sid = await self.ensure_session(conv_id)

        # 异步发送消息（不等待响应）
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(
                f"{self.base_url}/session/{sid}/prompt_async",
                json={
                    "agent": agent,
                    "parts": [{"type": "text", "text": message}],
                },
            )
        _log.info(f"消息已发送 conv_id={conv_id} sid={sid}")

        # 消费 SSE 事件流
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as c:
            async with c.stream("GET", f"{self.base_url}/event") as resp:
                event_type = ""
                async for line in resp.aiter_lines():
                    # SSE 协议解析
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                        continue
                    if not line.startswith("data:"):
                        continue

                    try:
                        raw = json.loads(line[5:])
                    except json.JSONDecodeError:
                        continue

                    # OpenCode /event 端点返回 GlobalEvent: {directory, payload}
                    # payload 才是真正的事件
                    event = raw.get("payload", raw)
                    props = event.get("properties", {})

                    # 过滤非本 session 的事件
                    event_session = (
                        props.get("sessionID")
                        or props.get("info", {}).get("sessionID")
                        or (props.get("part", {}) or {}).get("sessionID")
                    )
                    if event_session and event_session != sid:
                        continue

                    yield event

                    # session.idle 表示该 session 处理完毕
                    if event.get("type") == "session.idle":
                        if props.get("sessionID") == sid:
                            return
```

### 3.3 `opencode_adapter.py` — 事件转译（核心映射层）

这是整个方案最关键的文件。它把 OpenCode 的 Part-based 事件翻译为前端已有的 SSE 事件。

**OpenCode 的 Part 类型 → 前端 SSE 事件的映射关系：**

```
OpenCode Part 类型               前端 SSE 事件
─────────────────────────────    ─────────────────
ReasoningPart (type: reasoning)  → thinking
TextPart      (type: text)       → text
AgentPart     (type: agent)      → step_start（新 SubAgent 开始）
ToolPart      (type: tool)
  ├ state: running               → （记录开始时间）
  ├ state: completed             → sub_step（Skill 脚本执行完成）
  │   └ tool=get_skill_script    →   + 解析 stdout → render/wifi_result/...
  └ state: error                 → sub_step（标记错误）
StepFinishPart(type: step-finish)→ step_end
subtask Part  (type: subtask)    → step_start（Task tool 委派 SubAgent）
message.updated (completed)      → done
session.error                    → error
```

```python
"""OpenCode 事件 → 前端 SSE 协议转译器。

与 event_adapter.py 输出完全相同的 SSE 事件格式，
但数据源是 OpenCode Server 的 /event SSE 流而非 agno Team.arun 事件流。
"""
from __future__ import annotations
import json
import time
import uuid
from typing import Any, AsyncGenerator, Optional
from loguru import logger
from api.sse import format_sse
from api.event_adapter import (
    MessageAggregate,
    StepAggregate,
    _emit_insight_render,     # 复用 agno adapter 的业务解析函数
    _emit_wifi_result,
    _emit_experience_assurance_result,
    _emit_phase_render_blocks,
    _parse_stdout,
    _MEMBER_DISPLAY_NAMES,
)

_log = logger.bind(channel="opencode_adapter")

# OpenCode tool name → agno skill name 映射
# OpenCode 里工具名是 "get_skill_script"，skill_name 在 tool args 里
def _extract_skill_name(tool_input: dict) -> str:
    return tool_input.get("skill_name", "")


async def adapt_opencode(
    conv_id: str,
    event_stream: AsyncGenerator[dict, None],
) -> AsyncGenerator[tuple[str, MessageAggregate], None]:
    """消费 OpenCode 事件流，yield (SSE字符串, MessageAggregate) 元组。

    输出格式与 event_adapter.adapt() 完全一致，前端无感切换。
    """
    agg = MessageAggregate(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
    )

    # 状态追踪
    steps_by_agent: dict[str, StepAggregate] = {}
    current_agent: Optional[str] = None
    tool_start_times: dict[str, float] = {}   # callID → start_time
    tool_inputs: dict[str, dict] = {}         # callID → input
    thinking_start: Optional[float] = None
    thinking_end: Optional[float] = None

    try:
        async for event in event_stream:
            etype = event.get("type", "")
            props = event.get("properties", {})

            # ── message.part.updated — Part 级增量更新 ──────────────
            if etype == "message.part.updated":
                part = props.get("part", {})
                delta = props.get("delta")
                ptype = part.get("type", "")

                # ── reasoning → thinking ──
                if ptype == "reasoning":
                    if thinking_start is None:
                        thinking_start = time.monotonic()
                    content = delta or part.get("text", "")
                    if content:
                        agg.thinking_content += content
                        step_id = current_agent or ""
                        yield format_sse("thinking", {
                            "content": content,
                            "stepId": step_id,
                        }), agg

                # ── text → text ──
                elif ptype == "text":
                    content = delta or part.get("text", "")
                    if content:
                        agg.content += content
                        # 如果在某个 step 内，更新 step text
                        if current_agent and current_agent in steps_by_agent:
                            steps_by_agent[current_agent].text_content += content
                        yield format_sse("text", {"content": content}), agg

                # ── agent → step_start ──
                elif ptype == "agent":
                    agent_name = part.get("name", "")
                    if agent_name and agent_name not in steps_by_agent:
                        # 结束上一个 thinking 段（如果有）
                        if thinking_start and not thinking_end:
                            thinking_end = time.monotonic()

                        current_agent = agent_name
                        step = StepAggregate(
                            step_id=agent_name,
                            title=_MEMBER_DISPLAY_NAMES.get(
                                agent_name, agent_name
                            ),
                        )
                        steps_by_agent[agent_name] = step
                        agg.steps.append(step)

                        yield format_sse("step_start", {
                            "stepId": agent_name,
                            "title": step.title,
                        }), agg

                # ── subtask → step_start（Task tool 委派） ──
                elif ptype == "subtask":
                    agent_name = part.get("agent", "")
                    if agent_name and agent_name not in steps_by_agent:
                        current_agent = agent_name
                        step = StepAggregate(
                            step_id=agent_name,
                            title=_MEMBER_DISPLAY_NAMES.get(
                                agent_name, agent_name
                            ),
                        )
                        steps_by_agent[agent_name] = step
                        agg.steps.append(step)

                        yield format_sse("step_start", {
                            "stepId": agent_name,
                            "title": step.title,
                        }), agg

                # ── tool → sub_step 生命周期 ──
                elif ptype == "tool":
                    call_id = part.get("callID", "")
                    tool_name = part.get("tool", "")
                    state = part.get("state", {})
                    status = state.get("status", "")

                    if status == "running":
                        tool_start_times[call_id] = time.monotonic()
                        tool_inputs[call_id] = state.get("input", {})

                    elif status == "completed":
                        t0 = tool_start_times.pop(call_id, None)
                        duration_ms = int((time.monotonic() - t0) * 1000) if t0 else 0
                        tinput = tool_inputs.pop(call_id, {})
                        skill_name = _extract_skill_name(tinput)
                        stdout = state.get("output", "")
                        step_id = current_agent or ""

                        # 只为 get_skill_script 发 sub_step（与 agno adapter 对齐）
                        # get_skill_instructions / get_skill_reference 也发，但 name 不同
                        is_exec = tool_name == "get_skill_script" and tinput.get("execute", False)
                        is_load = tool_name in ("get_skill_instructions", "get_skill_reference")

                        if is_exec or is_load:
                            sub_step_id = f"{step_id}_{call_id}"
                            sub = {
                                "subStepId": sub_step_id,
                                "name": skill_name or tool_name,
                                "completedAt": "",
                                "durationMs": duration_ms,
                                "scriptPath": tinput.get("script_path", ""),
                                "callArgs": tinput.get("args", []),
                                "stdout": stdout[:2000] if is_exec else "",
                                "stderr": "",
                            }

                            if current_agent and current_agent in steps_by_agent:
                                steps_by_agent[current_agent].sub_steps.append(sub)
                                steps_by_agent[current_agent].items.append({
                                    "type": "sub_step", **sub
                                })

                            yield format_sse("sub_step", sub), agg

                        # ── 业务渲染块解析（复用 agno adapter 的函数）──
                        if is_exec and stdout:
                            yield from _emit_renders(
                                skill_name, stdout, sub_step_id,
                                step_id, agg,
                            )

                    elif status == "error":
                        error_msg = state.get("error", "工具执行失败")
                        _log.error(f"tool error: {tool_name} {error_msg}")

                # ── step-finish → step_end ──
                elif ptype == "step-finish":
                    if current_agent:
                        yield format_sse("step_end", {
                            "stepId": current_agent,
                        }), agg

                    # 提取 token 信息
                    tokens = part.get("tokens", {})
                    agg.input_tokens += tokens.get("input", 0)
                    agg.output_tokens += tokens.get("output", 0)
                    agg.reasoning_tokens += tokens.get("reasoning", 0)
                    agg.total_tokens = agg.input_tokens + agg.output_tokens

            # ── message.updated — 消息级状态更新 ──────────────────
            elif etype == "message.updated":
                info = props.get("info", {})
                if info.get("role") == "assistant":
                    tokens = info.get("tokens", {})
                    agg.input_tokens = tokens.get("input", 0)
                    agg.output_tokens = tokens.get("output", 0)
                    agg.reasoning_tokens = tokens.get("reasoning", 0)
                    agg.total_tokens = agg.input_tokens + agg.output_tokens

                    # 如果有 time.completed，说明消息已完成
                    if info.get("time", {}).get("completed"):
                        if thinking_start:
                            thinking_end = thinking_end or time.monotonic()
                            agg.thinking_duration_sec = int(
                                thinking_end - thinking_start
                            )
                        agg.status = "done"
                        yield format_sse("done", {
                            "messageId": agg.message_id,
                            "thinkingDurationSec": agg.thinking_duration_sec,
                            "inputTokens": agg.input_tokens,
                            "outputTokens": agg.output_tokens,
                            "totalTokens": agg.total_tokens,
                            "reasoningTokens": agg.reasoning_tokens,
                        }), agg
                        return

            # ── session.error ──────────────────────────────────────
            elif etype == "session.error":
                err_data = props.get("error", {})
                msg = err_data.get("data", {}).get("message", str(err_data))
                agg.status = "error"
                agg.error_message = msg
                yield format_sse("error", {"message": msg}), agg
                return

            # ── session.idle — 该 session 完成 ────────────────────
            elif etype == "session.idle":
                if agg.status == "streaming":
                    if thinking_start:
                        thinking_end = thinking_end or time.monotonic()
                        agg.thinking_duration_sec = int(
                            thinking_end - thinking_start
                        )
                    agg.status = "done"
                    yield format_sse("done", {
                        "messageId": agg.message_id,
                        "thinkingDurationSec": agg.thinking_duration_sec,
                        "inputTokens": agg.input_tokens,
                        "outputTokens": agg.output_tokens,
                        "totalTokens": agg.total_tokens,
                        "reasoningTokens": agg.reasoning_tokens,
                    }), agg
                return

    except Exception as exc:
        _log.exception("opencode_adapter 异常")
        agg.status = "error"
        agg.error_message = str(exc)
        yield format_sse("error", {"message": f"OpenCode 执行失败：{exc}"}), agg


def _emit_renders(
    skill_name: str,
    stdout: str,
    sub_step_id: str,
    step_id: str,
    agg: MessageAggregate,
):
    """复用 agno event_adapter 的业务渲染解析函数。

    从 get_skill_script 的 stdout 中提取 insight 图表、wifi 热力图等，
    产出 render / report / wifi_result / experience_assurance_result 事件。
    """
    # wifi_simulation 通道
    if skill_name == "wifi_simulation":
        parsed = _parse_stdout(stdout)
        if parsed and isinstance(parsed, dict):
            from api.event_adapter import _emit_wifi_result
            for rb in _emit_wifi_result(parsed):
                agg.render_blocks.append(rb)
                yield format_sse("wifi_result", rb), agg

    # experience_assurance 通道
    elif skill_name == "experience_assurance":
        from api.event_adapter import _emit_experience_assurance_result
        for rb in _emit_experience_assurance_result(stdout):
            agg.render_blocks.append(rb)
            yield format_sse("experience_assurance_result", rb), agg

    # insight 通道
    elif step_id == "insight":
        parsed = _parse_stdout(stdout)
        if isinstance(parsed, dict) and "results" in parsed:
            render_list = _emit_phase_render_blocks(parsed)
        else:
            render_list = _emit_insight_render(skill_name, stdout, sub_step_id)
        for rb in render_list:
            agg.render_blocks.append(rb)
            yield format_sse("report", rb), agg
            yield format_sse("render", rb), agg
```

### 3.4 `routes/messages.py` — 改动点

只在 `send_message` 函数中加一个引擎分发逻辑：

```python
# ── 在文件顶部新增 import ──
from api.engine_config import get_config

# ── send_message 函数内部，在 "先落业务库" 之后 ──

    engine_cfg = get_config()

    if engine_cfg["engine"] == "opencode":
        # ── OpenCode 通道 ──
        from api.opencode_bridge import OpenCodeClient
        from api.opencode_adapter import adapt_opencode

        oc = OpenCodeClient(base_url=engine_cfg["opencode_url"])
        raw_stream = oc.send_and_stream(
            conv_id, body.content,
            agent=engine_cfg.get("opencode_agent", "orchestrator"),
        )
        adapter = adapt_opencode(conv_id, raw_stream)
    else:
        # ── agno 通道（现有逻辑不变）──
        ctx = get_session_context(conv_id)
        # ... 现有 tracer/observability 代码 ...
        raw_stream = ctx.team.arun(
            body.content, session_id=conv_id,
            stream=True, stream_events=True,
        )
        adapter = adapt(
            conv_id, raw_stream,
            tracer=ctx.tracer,
            db_session_id=ctx.db_session_id,
            user_msg_id=user_msg_id,
        )

    # ── 以下 sse_generator 代码完全不变 ──
    async def sse_generator():
        ...  # 现有代码
```

### 3.5 `routes/engine.py` — 引擎配置 API

```python
"""GET/PUT /api/engine — 引擎切换。"""
from fastapi import APIRouter
from api.engine_config import get_config, set_config
from api.models import ok

router = APIRouter(prefix="/engine", tags=["engine"])

@router.get("")
async def get_engine():
    return ok(get_config())

@router.put("")
async def set_engine(body: dict):
    cfg = set_config(body)
    return ok(cfg)
```

在 `api/main.py` 中注册：

```python
from api.routes.engine import router as engine_router
app.include_router(engine_router, prefix="/api")
```

---

## 4. 前端改动（最小化）

### 4.1 改动范围

前端**不需要改**任何 SSE 消费逻辑、步骤卡渲染、业务面板渲染。只需加一个引擎切换入口。

### 4.2 唯一改动：设置区加一个切换

```typescript
// 在设置/偏好组件中新增：
const [engine, setEngine] = useState<'agno' | 'opencode'>('agno')

// 读取当前引擎
useEffect(() => {
  fetch('/api/engine').then(r => r.json()).then(d => setEngine(d.data.engine))
}, [])

// 切换引擎
const switchEngine = async (e: 'agno' | 'opencode') => {
  await fetch('/api/engine', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ engine: e })
  })
  setEngine(e)
}
```

UI 上可以是一个简单的 Toggle 或 Select：

```
引擎选择: [agno ▼] / [opencode ▼]
OpenCode 地址: http://127.0.0.1:4096  （仅 opencode 模式可编辑）
```

### 4.3 可选增强：连接状态指示

```typescript
// 定期轮询 OpenCode 健康状态
const [ocHealthy, setOcHealthy] = useState(false)
useEffect(() => {
  if (engine !== 'opencode') return
  const timer = setInterval(async () => {
    try {
      const r = await fetch('/api/engine/health')
      const d = await r.json()
      setOcHealthy(d.data.healthy)
    } catch { setOcHealthy(false) }
  }, 5000)
  return () => clearInterval(timer)
}, [engine])
```

后端对应加一个 `/api/engine/health` 端点：

```python
@router.get("/health")
async def engine_health():
    cfg = get_config()
    if cfg["engine"] == "opencode":
        from api.opencode_bridge import OpenCodeClient
        oc = OpenCodeClient(cfg["opencode_url"])
        healthy = await oc.health()
        return ok({"engine": "opencode", "healthy": healthy, "url": cfg["opencode_url"]})
    return ok({"engine": "agno", "healthy": True})
```

---

## 5. 启动与连接指南

### 5.1 完整启动流程（双引擎模式，4 个终端）

```bash
# ──────────────────────────────────────────────
# 终端 1：启动 OpenCode Server（headless 模式）
# ──────────────────────────────────────────────
cd /path/to/broadband-agent      # 项目根目录（含 opencode.json）
opencode serve --port 4096

# 预期输出:
#   OpenCode server listening on http://127.0.0.1:4096
#   OpenAPI spec available at http://127.0.0.1:4096/doc


# ──────────────────────────────────────────────
# 终端 2：启动 FastAPI 后端
# ──────────────────────────────────────────────
cd /path/to/broadband-agent
uv run python -m api.main
# 或
python -m api.main

# 预期输出:
#   FastAPI 服务启动，端口 8080


# ──────────────────────────────────────────────
# 终端 3：启动 React 前端
# ──────────────────────────────────────────────
cd /path/to/broadband-agent-demo/frontend
npm run dev

# 预期输出:
#   Local: http://localhost:5173


# ──────────────────────────────────────────────
# 终端 4（可选）：调试用 TUI — 连接到同一个 Server
# ──────────────────────────────────────────────
# 随时打开，不影响前端和后端的正常运行
opencode attach http://127.0.0.1:4096

# 进入 TUI 后你可以：
#   - 浏览所有前端发过来的 session（按快捷键打开 session 列表）
#   - 选中任意 session 查看完整对话历史
#   - 看到 Orchestrator 的 reasoning、Task tool 委派详情、每个 skill stdout
#   - 甚至在 TUI 里继续对话（调试某个 agent 的行为）
```

### 5.2 仅 agno 模式（向后兼容，无需 OpenCode）

```bash
# 只需启动 FastAPI + 前端，完全不需要 opencode serve
cd /path/to/broadband-agent
uv run python -m api.main        # 终端 1

cd /path/to/broadband-agent-demo/frontend
npm run dev                        # 终端 2

# data/engine.json 默认 engine=agno，无需任何配置
```

### 5.3 切换引擎

```bash
# 方式 1: 前端 UI 切换
# 打开设置页 → 引擎选择 → 切换到 opencode

# 方式 2: API 直接切换
curl -X PUT http://localhost:8080/api/engine \
  -H 'Content-Type: application/json' \
  -d '{"engine": "opencode", "opencode_url": "http://127.0.0.1:4096"}'

# 方式 3: 直接编辑配置文件
echo '{"engine": "opencode"}' > data/engine.json
```

### 5.4 连接验证清单

```bash
# 1. 验证 OpenCode Server 在线
curl http://127.0.0.1:4096/global/health
# 期望: {"healthy":true,"version":"..."}

# 2. 验证 FastAPI 在线
curl http://localhost:8080/health
# 期望: {"status":"ok"}

# 3. 验证引擎配置
curl http://localhost:8080/api/engine
# 期望: {"code":0,"data":{"engine":"opencode","opencode_url":"http://127.0.0.1:4096"}}

# 4. 验证 OpenCode 连通性（通过 FastAPI 代理）
curl http://localhost:8080/api/engine/health
# 期望: {"code":0,"data":{"engine":"opencode","healthy":true}}

# 5. 发一条消息测试端到端
curl -X POST http://localhost:8080/api/conversations/{conv_id}/messages \
  -H 'Content-Type: application/json' \
  -d '{"content": "你好"}' \
  --no-buffer
# 期望: SSE 流输出 event: text / event: done
```

### 5.5 进阶：一键启动脚本

```bash
#!/bin/bash
# scripts/start_all.sh — 启动全部服务

echo "Starting OpenCode Server..."
cd /path/to/broadband-agent
opencode serve --port 4096 &
OC_PID=$!

echo "Waiting for OpenCode Server..."
until curl -s http://127.0.0.1:4096/global/health > /dev/null 2>&1; do
  sleep 1
done
echo "OpenCode Server ready."

echo "Starting FastAPI..."
uv run python -m api.main &
API_PID=$!

echo "Starting Frontend..."
cd /path/to/broadband-agent-demo/frontend
npm run dev &
FE_PID=$!

echo "All services started."
echo "  OpenCode: http://127.0.0.1:4096 (PID: $OC_PID)"
echo "  FastAPI:  http://localhost:8080    (PID: $API_PID)"
echo "  Frontend: http://localhost:5173    (PID: $FE_PID)"
echo ""
echo "调试提示: 在新终端执行以下命令打开 TUI 查看会话历史:"
echo "  opencode attach http://127.0.0.1:4096"

trap "kill $OC_PID $API_PID $FE_PID" EXIT
wait
```

---

## 6. 事件映射对照表（完整）

| OpenCode 事件 | OpenCode Part.type | 前端 SSE 事件 | 说明 |
|---|---|---|---|
| message.part.updated | reasoning | `thinking` | ReasoningPart delta → thinking content |
| message.part.updated | text | `text` | TextPart delta → 最终回复文本 |
| message.part.updated | agent | `step_start` | AgentPart.name → stepId |
| message.part.updated | subtask | `step_start` | Task tool 委派，subtask.agent → stepId |
| message.part.updated | tool (running) | （内部记录） | 记录开始时间，不发前端事件 |
| message.part.updated | tool (completed) | `sub_step` | get_skill_script 完成 → subStep |
| message.part.updated | tool (completed) | `render` / `report` | insight stdout 解析 → 图表 |
| message.part.updated | tool (completed) | `wifi_result` | wifi stdout 解析 → 聚合结果 |
| message.part.updated | tool (completed) | `experience_assurance_result` | 体验保障结果 |
| message.part.updated | step-finish | `step_end` | step 结束 + token 统计 |
| message.updated | (completed) | `done` | 消息完成 + 总 token |
| session.error | — | `error` | 错误 |
| session.idle | — | `done`（兜底） | session 空闲 = 处理完毕 |

---

## 7. 已知限制与对策

### 7.1 OpenCode Server 必须在同一台机器

`opencode serve` 需要在项目目录下运行，因为它要读取 `opencode.json`、`.opencode/agents/`、`skills/` 等配置。FastAPI 通过 `localhost:4096` 访问它。

**对策**：这正是你当前的部署模型（前端 + 后端 + agents 同机）。

### 7.2 图片路径问题

agno 通道下，`event_adapter.py` 会把 wifi 仿真产出的 PNG 拷贝到 `data/images/`，前端通过 `/api/images/:id` 访问。OpenCode 通道下，skill 脚本产出的图片路径可能不同。

**对策**：在 `opencode_adapter.py` 的 `_emit_renders` 中，解析 stdout 里的图片路径后做同样的拷贝操作（从 `skills/wifi_simulation/data/` 拷到 `data/images/`）。这段逻辑可以直接从 `event_adapter.py` 的 `_handle_wifi_images` 复制过来。

### 7.3 会话历史隔离

agno 会话存在 `data/api.db`（由 `repository.py` 管理），OpenCode 会话存在 OpenCode 自己的 SQLite。两套不互通。

**对策**：`opencode_bridge.py` 用内存 dict 做 `conv_id → session_id` 映射。FastAPI 的 `repository.py` 继续负责前端的会话持久化（insert_user_message / insert_assistant_message），这部分代码在 `messages.py` 的 `sse_generator` 里，不受引擎切换影响。

### 7.4 Observability 与调试

agno 通道有 Tracer 写 `data/sessions.db`。OpenCode 通道有自己独立的一套 observability 体系（SQLite + CLI 工具链），不需要接入 agno Tracer。

**OpenCode 的 observability 反而更完整**——它原生记录了每一条消息、每一个 Part（包括 tool 调用的完整 input/output），并且提供了多种查看方式。详见下方 §9。

---

## 8. 调试与会话回溯

这是日常开发中最常用的操作。因为 TUI 和 Server 共享同一个 SQLite 数据库（`~/.local/share/opencode/opencode.db`），所有通过前端 bridge 创建的 session 在 TUI 和 CLI 中都完全可见。

### 8.1 用 TUI 查看前端的对话历史

```bash
# 前提：opencode serve --port 4096 已经在运行

# 在任意新终端连接到同一个 Server
opencode attach http://127.0.0.1:4096
```

进入 TUI 后，打开 session 列表（默认快捷键 `Leader + s`），你会看到：

```
  ┌─ Sessions ──────────────────────────────────────────┐
  │  broadband-a3f2   2 分钟前  "帮我查看小区的WIFI覆盖"  │
  │  broadband-b7c1   20 分钟前 "生成一份CEI洞察报告"      │
  │  broadband-e4d9   1 小时前  "配置差异化承载切片"        │
  │  test-session     3 小时前  "你好"                    │
  └─────────────────────────────────────────────────────┘
```

选中任意 session，能看到**完整的对话上下文**：

- Orchestrator 的 reasoning（为什么选择委派给 @planning 而不是 @insight）
- Task tool 委派的 payload（传给 SubAgent 的任务描述）
- 每个 `get_skill_script` 调用的完整 input 和 stdout
- SubAgent 的中间推理过程
- 最终拼装回复的全文

如果你发现某个对话有问题，可以**直接在 TUI 里继续对话**进行调试——TUI 里发的消息和前端发的消息共享同一个 session context。

### 8.2 跳转到特定 session

```bash
# 如果你已经知道 session ID（比如从日志里看到的）
opencode attach http://127.0.0.1:4096 --session <session-id>
```

### 8.3 用 CLI 查看和导出

不想开 TUI 的话，用 CLI 也可以：

```bash
# 列出所有 session（含标题和时间）
opencode session list

# 导出某个 session 的完整 JSON（含所有消息、Part、tool 调用）
opencode session export <session-id>

# 导出后可以用 jq 做分析
opencode session export <session-id> | jq '.messages[] | select(.role=="assistant") | .parts[] | select(.type=="tool") | {tool: .tool, status: .state.status}'
```

### 8.4 查看 token 用量和费用

```bash
# 查看所有 session 的汇总统计
opencode stats

# 输出类似：
#   Total Sessions: 15
#   Total Tokens: 1,234,567
#   Total Cost: $1.23
#   Model Usage:
#     dashscope/qwen3.5-397b-a17b: 12 sessions, 1.1M tokens
```

### 8.5 典型调试场景

**场景 1：前端显示"工具调用出错"**

```bash
# 1. 在 FastAPI 的 sse.log 里找到 conv_id
tail -f data/logs/sse.log | grep "error"

# 2. 从 opencode_bridge.py 的日志找到对应的 OpenCode session_id
#    日志格式: "OpenCode session 创建: conv_id=xxx → sid=yyy"

# 3. 在 TUI 里打开这个 session
opencode attach http://127.0.0.1:4096 --session <sid>

# 4. 翻看 tool Part 的 state.error 字段，看到完整的错误信息
#    比如："Script execution timed out after 30s"
#    或者："Error: skill 'cei_pipeline' not found"
```

**场景 2：SubAgent 路由不正确**

```bash
# 1. 在 TUI 里打开对应 session
# 2. 找到 Orchestrator 的 reasoning Part（type: reasoning）
#    看它的思考过程：为什么把"查看WIFI覆盖"路由给了 @insight 而不是 @provisioning-wifi
# 3. 根据 reasoning 内容决定是调 prompt 还是调路由关键词
```

**场景 3：insight 图表前端没渲染出来**

```bash
# 1. 导出 session JSON
opencode session export <sid> > /tmp/debug.json

# 2. 找到 insight_query 的 tool result
cat /tmp/debug.json | jq '
  .messages[].parts[]
  | select(.type=="tool" and .tool=="get_skill_script")
  | select(.state.input.skill_name=="insight_query")
  | .state.output' | head -100

# 3. 看 stdout 里的 chart_configs 是否完整、JSON 是否合法
# 4. 如果 stdout 正常但前端没渲染，问题在 opencode_adapter 的 _emit_renders
```

### 8.6 调试时的注意事项

- **TUI 和前端可以同时使用**：attach 进 TUI 不会影响前端的 SSE 流，两者消费的是不同的客户端连接
- **TUI 里可以发消息**：但要注意如果前端也在同一个 session 里发消息，会产生交叉（建议调试时用 TUI 发，观察时用前端看，避免同时发）
- **session 数据持久化**：即使 `opencode serve` 重启，历史 session 也不丢失（数据在 SQLite 里）
- **conv_id → session_id 映射**：这个映射在 `opencode_bridge.py` 的内存 dict 里，FastAPI 重启后会丢失（但不影响功能——下次同一个 conv_id 会创建新的 OpenCode session）。如果需要持久化映射，后续可以写入 `data/engine.json` 或 `data/api.db`

---

## 9. 实施步骤与工作量

| 阶段 | 内容 | 预估工时 |
|------|------|----------|
| P1 | `engine_config.py` + `routes/engine.py` + 注册路由 | 0.5 天 |
| P2 | `opencode_bridge.py` — Session 管理 + SSE 消费 | 1-2 天 |
| P3 | `opencode_adapter.py` — 核心事件映射（thinking/text/step/sub_step/done） | 2-3 天 |
| P4 | `opencode_adapter.py` — 业务渲染块（insight/wifi/assurance 复用） | 1-2 天 |
| P5 | `messages.py` 引擎分发改造 | 0.5 天 |
| P6 | 前端引擎切换 UI | 0.5 天 |
| P7 | 端到端联调 + 边界处理 | 1-2 天 |
| **合计** | | **6-10 天** |

建议 P1→P2→P3 串行（搭建管道），P4 可以和 P3 并行（不同的渲染块互不干扰），P5→P6→P7 串行（集成测试）。
