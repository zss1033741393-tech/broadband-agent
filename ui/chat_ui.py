"""Gradio 调试界面 — Claude 风格折叠式消息（多 Agent 架构）

每轮对话以折叠式活动日志呈现（Gradio ChatMessage + MetadataDict）：
  🤖 子Agent — 可折叠块，活跃时旋转图标，完成后自动折叠
    💭 思考  — 嵌套在 Agent 块内，thinking 完成后折叠
    🔧 工具  — 嵌套在 Agent 块内，每个工具独立折叠，含中文说明+耗时
    子Agent回复 — 嵌套在 Agent 块内，不折叠（普通文本）
  💬 回答    — 最终回答，普通消息不折叠

思考内容来源（三条路径）：
  1. ReasoningContentDeltaEvent — deepseek-reasoner / o1 等原生推理模型
  2. RunContentEvent.reasoning_content — 模型 API 返回的 reasoning_content 字段
  3. RunContentEvent.content 中的 <think>...</think> — qwen3 native thinking

多 Agent 事件来源：
  - RunEvent.*       — 子 Agent（IntentAgent 等）产生的事件
  - TeamRunEvent.*   — 主控 OrchestratorTeam 产生的事件
  两类事件均被捕获并统一渲染。

独立启动：python ui/chat_ui.py（监听 7860 端口，与 AgentOS 进程分离）
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

import gradio as gr
from gradio.components.chatbot import ChatMessage

from agno.run.agent import RunEvent
from agno.run.team import TeamRunEvent
from app.agent.agent import get_agent
from app.logger.setup import setup_logging
from app.outputs.sink import set_current_session_id

setup_logging()

logger = logging.getLogger("chat_ui")


# ─────────────────────────────────────────────────────────────
# <think> 标签流式解析器（qwen3 native thinking）
# ─────────────────────────────────────────────────────────────

class _ThinkTagParser:
    """从流式 content delta 中分离 <think>...</think> 块。

    Agno 在流式模式下不提取 qwen3 的 <think> 标签（仅非流式路径提取），
    因此需要在 UI 层手动解析。采用状态机 + 缓冲区处理跨 delta 的标签边界。
    """

    _OPEN = "<think>"
    _CLOSE = "</think>"

    def __init__(self) -> None:
        self._in_think = False
        self._buf = ""

    def feed(self, delta: str) -> list[tuple[str, str]]:
        """输入一个 content delta，返回 [(kind, text), ...].

        kind 为 "think" 或 "content"。
        """
        self._buf += delta
        chunks: list[tuple[str, str]] = []
        while True:
            if self._in_think:
                idx = self._buf.find(self._CLOSE)
                if idx >= 0:
                    think_text = self._buf[:idx]
                    self._buf = self._buf[idx + len(self._CLOSE):]
                    self._in_think = False
                    if think_text:
                        chunks.append(("think", think_text))
                else:
                    # 未见 </think>，保留末尾可能的部分标签
                    safe = len(self._buf) - len(self._CLOSE) + 1
                    if safe > 0:
                        chunks.append(("think", self._buf[:safe]))
                        self._buf = self._buf[safe:]
                    break
            else:
                idx = self._buf.find(self._OPEN)
                if idx >= 0:
                    before = self._buf[:idx]
                    self._buf = self._buf[idx + len(self._OPEN):]
                    self._in_think = True
                    if before:
                        chunks.append(("content", before))
                else:
                    safe = len(self._buf) - len(self._OPEN) + 1
                    if safe > 0:
                        chunks.append(("content", self._buf[:safe]))
                        self._buf = self._buf[safe:]
                    break
        return chunks

    def flush(self) -> list[tuple[str, str]]:
        """流结束时清空缓冲区。"""
        if self._buf:
            kind = "think" if self._in_think else "content"
            result = [(kind, self._buf)]
            self._buf = ""
            return result
        return []


# ─────────────────────────────────────────────────────────────
# 工具结果格式化
# ─────────────────────────────────────────────────────────────

def _format_result(result: Any) -> str:
    """将工具返回值格式化为可读字符串"""
    if result is None:
        return "(空)"
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception:
            return str(result)
    s = str(result)
    if len(s) > 1000:
        s = s[:1000] + f"\n...(已截断，共 {len(s)} 字符)"
    return s


# ─────────────────────────────────────────────────────────────
# Claude 风格消息构建器（数据模型驱动）
# ─────────────────────────────────────────────────────────────

# ── 工具名称 → 中文显示标题 ─────────────────────────────────
_TOOL_LABELS: dict[str, str] = {
    "get_skill_instructions": "📖 读取技能指南",
    "get_skill_script": "⚙️ 执行技能脚本",
    "get_skill_reference": "📚 读取参考资料",
    "get_pipeline_file": "📂 读取阶段产出",
    "analyze_intent": "🎯 意图解析与画像补全",
    "generate_plans": "📝 生成优化方案",
    "check_constraints": "✅ 约束校验",
    "translate_configs": "🔄 配置转译",
}


def _tool_display_title(name: str, args: dict[str, Any]) -> str:
    """根据工具名 + 参数生成可读的中文折叠标题。"""
    label = _TOOL_LABELS.get(name)
    if label is None:
        return f"🔧 {name}"

    # 从参数中提取关键信息作为补充说明
    detail = ""
    if name == "get_skill_instructions":
        detail = args.get("skill_name", "")
    elif name == "get_skill_script":
        skill = args.get("skill_name", "")
        script = args.get("script", "")
        detail = f"{skill}/{script}" if skill and script else skill or script
    elif name == "get_skill_reference":
        skill = args.get("skill_name", "")
        path = args.get("path", "")
        detail = f"{skill}/{path}" if skill and path else skill or path
    elif name == "get_pipeline_file":
        detail = args.get("stage", "")
    elif name == "generate_plans":
        f = args.get("intent_file", "")
        detail = f.rsplit("/", 1)[-1] if "/" in f else (f.rsplit("\\", 1)[-1] if "\\" in f else f)
    elif name in ("check_constraints", "translate_configs"):
        plans = args.get("plans_file", "")
        if plans:
            detail = plans.rsplit("/", 1)[-1] if "/" in plans else plans

    if detail:
        return f"{label} — {detail}"
    return label


class _MessageBuilder:
    """数据模型驱动的消息构建器。

    架构：事件 → 更新内部数据模型 → snapshot() 从数据模型渲染 ChatMessage 列表。
    每次 snapshot() 都是全量重建，不依赖 ChatMessage 的可变状态。

    数据模型：
      plan         — 主控协调文本
      agents[]     — 子 Agent 列表，每个含 items（思考/工具）+ content（正文）
      answer       — 主控最终回答
      errors[]     — 错误消息

    渲染顺序保证（每个 Agent 内部）：
      💭 思考(折叠) → 🔧 工具(折叠) → 💭 思考 → 🔧 工具 → ... → 📝 正文(不折叠，始终最后)
    """

    def __init__(self) -> None:
        self._plan = ""
        self._plan_done = False
        # 每个 agent: {name, id, items: [{type, ...}], content: str, status}
        self._agents: list[dict[str, Any]] = []
        self._answer = ""
        self._errors: list[str] = []
        self._agent_id_counter = 0
        self._tool_start_time: float | None = None

    # ── 内部辅助 ─────────────────────────────────────────────

    @property
    def _current(self) -> dict[str, Any] | None:
        """当前活跃的子 Agent（status=pending），没有则返回 None"""
        if self._agents and self._agents[-1]["status"] == "pending":
            return self._agents[-1]
        return None

    def _current_thinking(self, agent: dict[str, Any]) -> dict[str, Any] | None:
        """当前 Agent 最后一个未关闭的 thinking 块"""
        items = agent["items"]
        if items and items[-1]["type"] == "thinking" and items[-1]["status"] == "pending":
            return items[-1]
        return None

    def _close_thinking(self, agent: dict[str, Any]) -> None:
        t = self._current_thinking(agent)
        if t:
            t["status"] = "done"

    def _find_pending_tool(self, agent: dict[str, Any]) -> dict[str, Any] | None:
        for item in reversed(agent["items"]):
            if item["type"] == "tool" and item["status"] == "pending":
                return item
        return None

    def _close_agent(self, agent: dict[str, Any]) -> None:
        self._close_thinking(agent)
        agent["status"] = "done"

    # ── 事件处理（公开接口，与 _stream_chat 事件分发对应）──

    def on_member_start(self, member_name: str) -> None:
        """主控委托给子 Agent"""
        if self._current:
            self._close_agent(self._current)
        self._plan_done = True
        self._agent_id_counter += 1
        self._agents.append({
            "name": member_name,
            "id": f"agent_{self._agent_id_counter}",
            "items": [],
            "content": "",
            "status": "pending",
        })

    def on_plan(self, delta: str) -> None:
        """主控委托前的规划文本"""
        self._plan += delta

    def _ensure_agent(self) -> dict[str, Any]:
        """确保存在活跃 Agent，没有则自动创建。防御性兜底。"""
        if self._current is None:
            self.on_member_start("Agent")
        return self._current  # type: ignore[return-value]

    def on_thinking_delta(self, delta: str) -> None:
        """思考内容（reasoning / <think> / intermediate）"""
        agent = self._ensure_agent()
        t = self._current_thinking(agent)
        if t:
            t["text"] += delta
        else:
            agent["items"].append({
                "type": "thinking", "text": delta, "status": "pending",
            })

    def on_member_content_delta(self, delta: str) -> None:
        """子 Agent 正文 — 累积到 content 字段，snapshot 时始终渲染在工具之后"""
        agent = self._ensure_agent()
        self._close_thinking(agent)
        agent["content"] += delta

    def on_tool_start(self, name: str, args: dict[str, Any]) -> None:
        """工具调用开始"""
        agent = self._ensure_agent()
        self._close_thinking(agent)
        self._tool_start_time = time.monotonic()

        args_clean = {k: v for k, v in args.items() if k not in ("args", "kwargs")}
        content = (
            f"**参数**\n```json\n{json.dumps(args_clean, ensure_ascii=False, indent=2)}\n```\n\n*执行中...*"
            if args_clean else "*执行中...*"
        )
        item: dict[str, Any] = {
            "type": "tool",
            "title": _tool_display_title(name, args),
            "content": content,
            "status": "pending",
            "duration": None,
        }
        agent["items"].append(item)

    def on_tool_complete(self, name: str, result: Any) -> None:
        """工具调用完成"""
        agent = self._current or (self._agents[-1] if self._agents else None)
        if not agent:
            return
        tool = self._find_pending_tool(agent)
        if not tool:
            return
        tool["content"] = tool["content"].replace("\n\n*执行中...*", "").replace("*执行中...*", "")
        result_str = _format_result(result)
        tool["content"] += f"\n\n✅ **返回**\n```\n{result_str}\n```"
        tool["status"] = "done"
        if self._tool_start_time is not None:
            tool["duration"] = round(time.monotonic() - self._tool_start_time, 1)
            self._tool_start_time = None

    def on_tool_error(self, name: str, error: str) -> None:
        """工具调用出错"""
        agent = self._current or (self._agents[-1] if self._agents else None)
        if not agent:
            return
        tool = self._find_pending_tool(agent)
        if not tool:
            return
        tool["content"] = tool["content"].replace("\n\n*执行中...*", "").replace("*执行中...*", "")
        tool["content"] += f"\n\n❌ **错误** `{error}`"
        tool["status"] = "done"
        if self._tool_start_time is not None:
            tool["duration"] = round(time.monotonic() - self._tool_start_time, 1)
            self._tool_start_time = None

    def on_answer_delta(self, delta: str) -> None:
        """主控最终回答"""
        if self._current:
            self._close_agent(self._current)
        self._plan_done = True
        self._answer += delta

    def on_error(self, error_msg: str) -> None:
        self._errors.append(error_msg)

    def finalize(self) -> None:
        """流结束，关闭所有未完成块"""
        if self._current:
            self._close_agent(self._current)
        self._plan_done = True

    # ── 渲染：从数据模型生成 ChatMessage 列表 ────────────────

    def snapshot(self) -> list[ChatMessage]:
        """全量重建 ChatMessage 列表。

        渲染顺序：
          📋 协调（折叠）
          🤖 Agent 1（折叠）
            💭 思考（折叠，嵌套）
            🔧 工具（折叠，嵌套）
            📝 正文（不折叠，嵌套，始终在最后）
          🤖 Agent 2（折叠）
            ...
          ─── 分隔线 ───
          💬 最终回答（不折叠）
        """
        msgs: list[ChatMessage] = []

        # 1. 主控协调
        if self._plan.strip():
            msgs.append(ChatMessage(
                content=self._plan,
                metadata={"title": "📋 协调", "status": "done" if self._plan_done else "pending"},
            ))

        # 2. 子 Agent 块
        for agent in self._agents:
            # Agent 手风琴（父级）
            msgs.append(ChatMessage(
                content="",
                metadata={
                    "title": f"🤖 {agent['name']}",
                    "status": agent["status"],
                    "id": agent["id"],
                },
            ))

            # items：思考 + 工具（保持原始顺序）
            for item in agent["items"]:
                if item["type"] == "thinking" and item["text"].strip():
                    msgs.append(ChatMessage(
                        content=item["text"],
                        metadata={
                            "title": "💭 思考",
                            "status": item["status"],
                            "parent_id": agent["id"],
                        },
                    ))
                elif item["type"] == "tool":
                    meta: dict[str, Any] = {
                        "title": item["title"],
                        "status": item["status"],
                        "parent_id": agent["id"],
                    }
                    if item["duration"] is not None:
                        meta["duration"] = item["duration"]
                    msgs.append(ChatMessage(content=item["content"], metadata=meta))

            # 正文（始终在 items 之后，不折叠）
            if agent["content"].strip():
                msgs.append(ChatMessage(
                    content=agent["content"],
                    metadata={"parent_id": agent["id"]},
                ))

        # 3. 分隔线 + 最终回答
        if self._answer.strip():
            if msgs:
                msgs.append(ChatMessage(content="\n---\n"))
            msgs.append(ChatMessage(content=self._answer))

        # 4. 错误
        for err in self._errors:
            msgs.append(ChatMessage(
                content=f"**错误**\n\n{err}",
                metadata={"title": "❌ 错误", "status": "done"},
            ))

        return msgs


# ─────────────────────────────────────────────────────────────
# 事件类型常量集合（统一处理 RunEvent + TeamRunEvent）
# ─────────────────────────────────────────────────────────────

_TOOL_START  = {RunEvent.tool_call_started.value,   TeamRunEvent.tool_call_started.value}
_TOOL_DONE   = {RunEvent.tool_call_completed.value,  TeamRunEvent.tool_call_completed.value}
_TOOL_ERR    = {RunEvent.tool_call_error.value,      TeamRunEvent.tool_call_error.value}

# 主控委托前的规划文本（与最终回答分开渲染）
_CONTENT_PLAN  = {TeamRunEvent.run_intermediate_content.value}
# 子 Agent 中间内容（仅 output_model 场景下才发出，一般不触发）
_MEMBER_INTERMEDIATE = {RunEvent.run_intermediate_content.value}
# 子 Agent 最终回复（专家 Agent 完成后的输出）
_MEMBER_CONTENT = {RunEvent.run_content.value}
# 主控最终回答（Orchestrator 完成后的最终文本）
_TEAM_CONTENT   = {TeamRunEvent.run_content.value}

_ERROR     = {RunEvent.run_error.value,              TeamRunEvent.run_error.value}
_REASONING = {
    RunEvent.reasoning_content_delta.value,
    TeamRunEvent.reasoning_content_delta.value,
}
_MEMBER_START = {RunEvent.run_started.value, TeamRunEvent.task_iteration_started.value}

# 需要立即 yield 的重要事件（状态转变型）
_IMPORTANT_EVENTS = _TOOL_START | _TOOL_DONE | _TOOL_ERR | _MEMBER_START | _ERROR

# 已知但不需渲染的事件（避免 debug 噪音）
_KNOWN_SILENT = {
    RunEvent.run_completed.value,
    RunEvent.run_content_completed.value,
    RunEvent.reasoning_started.value,
    RunEvent.reasoning_completed.value,
    RunEvent.reasoning_step.value,
    RunEvent.model_request_started.value,
    RunEvent.model_request_completed.value,
    RunEvent.memory_update_started.value,
    RunEvent.memory_update_completed.value,
}

# 流式 delta 事件的 yield 最小间隔（秒），避免过度刷新
_YIELD_INTERVAL = 0.08


# ─────────────────────────────────────────────────────────────
# 内容事件通用处理 — 提取 reasoning_content + <think> 标签
# ─────────────────────────────────────────────────────────────

def _dispatch_content_event(
    event: Any,
    builder: _MessageBuilder,
    parser: _ThinkTagParser,
    content_handler,
) -> bool:
    """处理一个 content 事件，提取思考内容并分发。

    Returns: 是否有内容产生
    """
    has_content = False

    # 路径 1：模型 API 级别的 reasoning_content
    reasoning = getattr(event, "reasoning_content", None)
    if reasoning:
        builder.on_thinking_delta(reasoning)
        has_content = True

    # 路径 2+3：解析 content 中的 <think> 标签，剩余交给 content_handler
    content = getattr(event, "content", None)
    if content:
        chunks = parser.feed(content)
        for kind, text in chunks:
            if kind == "think":
                builder.on_thinking_delta(text)
            else:
                content_handler(text)
            has_content = True

    return has_content


# ─────────────────────────────────────────────────────────────
# 流式对话核心 — 供 Gradio ChatInterface 调用
# ─────────────────────────────────────────────────────────────

# 当前活跃会话 ID（调试 UI 单用户场景，模块级变量即可）
_active_session_id: str | None = None


async def _stream_chat(
    message: str, history: list,
) -> AsyncIterator[list[ChatMessage]]:
    """Claude 风格折叠式消息异步生成器。

    每次 yield 一个 ChatMessage 列表，ChatInterface._stream_fn 会用它
    替换（非追加）当前助手响应。

    节流策略：重要事件（工具开始/完成、Agent 开始、错误）立即 yield；
    delta 类事件按 _YIELD_INTERVAL 间隔合并 yield，减少 SSE 开销。
    """
    global _active_session_id
    # 新对话（history 为空）→ 生成新 session_id，避免历史污染
    if not history:
        _active_session_id = str(uuid.uuid4())
    session_id = _active_session_id
    # 提前设置 session_id，确保 get_pipeline_file 等工具可用
    set_current_session_id(session_id)

    team = get_agent()
    builder = _MessageBuilder()
    has_yielded = False
    pending_yield = False
    last_yield_time = 0.0
    member_parser = _ThinkTagParser()
    team_parser = _ThinkTagParser()

    try:
        async for event in team.arun(message, stream=True, stream_events=True, session_id=session_id):
            event_type = getattr(event, "event", None)
            tool = getattr(event, "tool", None)
            content_changed = False

            if event_type in _TOOL_START:
                name = getattr(tool, "tool_name", "?") if tool else "?"
                args = getattr(tool, "tool_args", {}) or {}
                builder.on_tool_start(name, args)
                content_changed = True

            elif event_type in _TOOL_DONE:
                name = getattr(tool, "tool_name", "?") if tool else "?"
                result = getattr(tool, "result", None)
                builder.on_tool_complete(name, result)
                content_changed = True

            elif event_type in _TOOL_ERR:
                name = getattr(tool, "tool_name", "?") if tool else "?"
                error = getattr(tool, "tool_call_error", "未知错误") or "未知错误"
                builder.on_tool_error(name, str(error))
                content_changed = True

            elif event_type in _CONTENT_PLAN:
                content = getattr(event, "content", None)
                if content:
                    builder.on_plan(content)
                    content_changed = True

            elif event_type in _MEMBER_INTERMEDIATE:
                content = getattr(event, "content", None)
                if content:
                    builder.on_thinking_delta(content)
                    content_changed = True

            elif event_type in _MEMBER_CONTENT:
                content_changed = _dispatch_content_event(
                    event, builder, member_parser, builder.on_member_content_delta
                )

            elif event_type in _TEAM_CONTENT:
                content_changed = _dispatch_content_event(
                    event, builder, team_parser, builder.on_answer_delta
                )

            elif event_type in _REASONING:
                delta = (
                    getattr(event, "reasoning_content", None)
                    or getattr(event, "content", None)
                )
                if delta:
                    builder.on_thinking_delta(delta)
                    content_changed = True

            elif event_type in _MEMBER_START:
                member_name = (
                    getattr(event, "member_name", None)
                    or getattr(event, "agent_name", None)
                    or getattr(event, "name", None)
                )
                if member_name:
                    for chunk_kind, chunk_text in member_parser.flush():
                        if chunk_kind == "think":
                            builder.on_thinking_delta(chunk_text)
                        else:
                            builder.on_member_content_delta(chunk_text)
                    builder.on_member_start(member_name)
                    content_changed = True

            elif event_type in _ERROR:
                error_msg = getattr(event, "error", "未知错误")
                builder.on_error(str(error_msg))
                has_yielded = True
                yield builder.snapshot()
                return

            elif event_type not in _KNOWN_SILENT:
                attrs = {k: v for k, v in vars(event).items()
                         if not k.startswith("_") and k != "event"}
                logger.debug("未处理事件 type=%s attrs=%s", event_type, list(attrs.keys()))

            # ── 节流 yield ────────────────────────────────────
            if content_changed:
                now = time.monotonic()
                if event_type in _IMPORTANT_EVENTS or (now - last_yield_time) >= _YIELD_INTERVAL:
                    has_yielded = True
                    last_yield_time = now
                    yield builder.snapshot()
                else:
                    pending_yield = True

        # 流结束：清空所有 parser 缓冲区
        for chunk_kind, chunk_text in member_parser.flush():
            if chunk_kind == "think":
                builder.on_thinking_delta(chunk_text)
            else:
                builder.on_member_content_delta(chunk_text)
        for chunk_kind, chunk_text in team_parser.flush():
            if chunk_kind == "think":
                builder.on_thinking_delta(chunk_text)
            else:
                builder.on_answer_delta(chunk_text)

    except Exception as exc:
        logger.exception("_stream_chat error")
        builder.on_error(str(exc))
        has_yielded = True
        yield builder.snapshot()

    # 关闭所有未完成块，yield 最终快照
    builder.finalize()
    final = builder.snapshot()
    if final:
        has_yielded = True
        yield final

    if not has_yielded:
        yield [ChatMessage(
            content=(
                "**[提示]** Team 未返回任何内容。\n\n"
                "常见原因：`configs/llm.yaml` 中 `reasoning: true` 对当前模型无效。\n"
                "qwen3 / 普通 OpenAI 兼容模型请设置 `reasoning: false`。"
            ),
        )]


# ─────────────────────────────────────────────────────────────
# Gradio UI 构建
# ─────────────────────────────────────────────────────────────

# Claude 风格视觉层级 CSS —— 折叠块（思考/工具/推理）与正式回答之间拉开区分度
_CUSTOM_CSS = """\
/* ── 折叠块：左侧色条 + 底色，形成"活动日志"视觉层级 ── */
#chatbot details {
    border-left: 3px solid #6366f1;
    background: #f7f7fb;
    border-radius: 8px;
    padding: 4px 12px;
    margin: 8px 0;
}
#chatbot details[open] {
    padding-bottom: 8px;
}
#chatbot details summary {
    padding: 4px 0;
    opacity: 0.85;
}
/* ── 分隔线样式（回答前的 ─── 横线） ── */
#chatbot hr {
    border: none;
    border-top: 1.5px solid #d4d4d8;
    margin: 16px 0 8px;
}
/* ── 暗色模式适配 ── */
.dark #chatbot details {
    border-left-color: #818cf8;
    background: rgba(99, 102, 241, 0.06);
}
.dark #chatbot hr {
    border-top-color: #3f3f46;
}
"""


def create_ui() -> gr.ChatInterface:
    chatbot = gr.Chatbot(
        height=700,
        elem_id="chatbot",
    )
    ci = gr.ChatInterface(
        fn=_stream_chat,
        chatbot=chatbot,
        title="家宽 CEI 体验优化 Agent — 调试界面",
        description=(
            "Claude 风格折叠式活动日志：🤖 子Agent（可折叠）→ 💭 思考（嵌套折叠）"
            "→ 🔧 工具调用（嵌套折叠）→ 💬 最终回答（不折叠）"
        ),
        examples=[
            "我是直播用户，晚上 8 点到 12 点需要保障上行带宽，对卡顿比较敏感",
            "帮我优化家里的网络，最近打游戏延迟很高",
            "视频会议老是卡，主要用腾讯会议，工作时间 9-18 点",
        ],
    )
    ci.css = _CUSTOM_CSS
    ci._deprecated_css = _CUSTOM_CSS
    return ci


if __name__ == "__main__":
    ui = create_ui()
    ui.launch(server_name="0.0.0.0", server_port=7860, share=False)
