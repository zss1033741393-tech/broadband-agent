"""Gradio 调试界面 — 结构化活动日志（多 Agent 架构）

每轮对话以分区块的活动日志呈现：
  🤖 子Agent — 主控委托给某个子 Agent（IntentAgent / PlanAgent / ...）
  📋 协调    — 主控委托前的规划文本（run_intermediate_content）
  💭 思考    — 模型 thinking（native reasoning / qwen3 <think> / 子 Agent 中间推理）
  🔧 工具    — 每次工具调用：工具名 + 参数（调用中 / 返回内容 / 错误）
  💬 回答    — 最终模型回复（TeamRunEvent.run_content）

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
from typing import Any, AsyncIterator

import gradio as gr

from agno.run.agent import RunEvent
from agno.run.team import TeamRunEvent
from app.agent.agent import get_agent
from app.logger.setup import setup_logging

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
# 活动日志数据结构
# ─────────────────────────────────────────────────────────────

class _Section:
    """日志中的一个显示块"""
    __slots__ = ("kind", "lines", "closed")

    def __init__(self, kind: str, initial: str = ""):
        self.kind: str = kind        # "member"|"plan"|"thinking"|"tool"|"answer"|"member_answer"|"error"
        self.lines: list[str] = [initial] if initial else []
        self.closed: bool = False

    def append(self, text: str) -> None:
        self.lines.append(text)

    def extend_last(self, delta: str) -> None:
        if self.lines:
            self.lines[-1] += delta
        else:
            self.lines.append(delta)

    def text(self) -> str:
        return "".join(self.lines)


class _ActivityLog:
    """维护本轮对话的结构化日志并生成 Markdown 渲染字符串"""

    _SEP = "\n\n---\n\n"

    def __init__(self) -> None:
        self._sections: list[_Section] = []
        self._tool_count = 0

    # ── 事件处理 ──────────────────────────────────────────────

    def on_member_start(self, member_name: str) -> None:
        """主控委托给子 Agent"""
        self._sections.append(_Section("member", f"**🤖 {member_name}**"))

    def on_plan(self, delta: str) -> None:
        """主控委托前的规划文本（run_intermediate_content），与最终回答区分"""
        sec = self._last("plan")
        if sec and not sec.closed:
            sec.extend_last(delta)
        else:
            new_sec = _Section("plan")
            new_sec.append(f"**📋 协调**\n\n{delta}")
            self._sections.append(new_sec)

    def on_thinking_delta(self, delta: str) -> None:
        """thinking delta（reasoning / <think> / intermediate）"""
        sec = self._last("thinking")
        if sec and not sec.closed:
            sec.extend_last(delta)
        else:
            self._sections.append(_Section("thinking", delta))

    def on_member_content_delta(self, delta: str) -> None:
        """子 Agent 最终回复（RunEvent.run_content），与主控回答区分"""
        # 关闭前面的 thinking 块（子 Agent 完成推理后输出最终内容）
        self._close_kind("thinking")
        sec = self._last("member_answer")
        if sec and not sec.closed:
            sec.extend_last(delta)
        else:
            new_sec = _Section("member_answer")
            new_sec.append(delta)
            self._sections.append(new_sec)

    def on_tool_start(self, name: str, args: dict[str, Any]) -> None:
        # 关闭当前 plan / thinking / member_answer 块，后续内容属于工具阶段
        self._close_kind("plan")
        self._close_kind("thinking")
        self._close_kind("member_answer")

        self._tool_count += 1
        header = f"**🔧 工具 #{self._tool_count}** `{name}`"
        args_clean = {k: v for k, v in args.items() if k not in ("args", "kwargs")}
        if args_clean:
            args_str = json.dumps(args_clean, ensure_ascii=False, indent=2)
            header += f"\n\n```json\n{args_str}\n```"
        header += "\n\n*执行中…*"
        sec = _Section("tool", header)
        self._sections.append(sec)

    def on_tool_complete(self, name: str, result: Any) -> None:
        sec = self._last_open_tool()
        if sec is None:
            return
        lines = sec.text().replace("\n\n*执行中…*", "")
        result_str = _format_result(result)
        lines += f"\n\n✅ **返回**\n\n```\n{result_str}\n```"
        sec.lines = [lines]
        sec.closed = True

    def on_tool_error(self, name: str, error: str) -> None:
        sec = self._last_open_tool()
        if sec is None:
            return
        lines = sec.text().replace("\n\n*执行中…*", "")
        lines += f"\n\n❌ **错误** `{error}`"
        sec.lines = [lines]
        sec.closed = True

    def on_answer_delta(self, delta: str) -> None:
        """主控最终回答（TeamRunEvent.run_content）"""
        # 关闭子 Agent 回复块，主控回答是新的阶段
        self._close_kind("member_answer")
        self._close_kind("thinking")
        sec = self._last("answer")
        if sec and not sec.closed:
            sec.extend_last(delta)
        else:
            new_sec = _Section("answer")
            new_sec.append(f"**💬 回答**\n\n{delta}")
            self._sections.append(new_sec)

    def on_error(self, msg: str) -> None:
        self._sections.append(_Section("error", f"**❌ 错误** {msg}"))

    # ── 渲染 ─────────────────────────────────────────────────

    def render(self) -> str:
        parts: list[str] = []
        for sec in self._sections:
            raw = sec.text()
            if not raw.strip():
                continue
            if sec.kind == "thinking":
                quoted = "\n".join(f"> {line}" for line in raw.splitlines())
                parts.append(f"**💭 思考**\n\n{quoted}")
            elif sec.kind == "member_answer":
                # 子 Agent 回复不加标题前缀（内容本身已经有结构化格式）
                # 与主控回答通过分隔线区分
                parts.append(raw)
            else:
                parts.append(raw)
        return self._SEP.join(parts) if parts else ""

    # ── 内部工具 ─────────────────────────────────────────────

    def _close_kind(self, kind: str) -> None:
        """关闭指定类型的最后一个未关闭 section"""
        sec = self._last(kind)
        if sec and not sec.closed:
            sec.closed = True

    def _last(self, kind: str) -> "_Section | None":
        for sec in reversed(self._sections):
            if sec.kind == kind:
                return sec
        return None

    def _last_open_tool(self) -> "_Section | None":
        for sec in reversed(self._sections):
            if sec.kind == "tool" and not sec.closed:
                return sec
        return None


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
    # 截断过长内容（避免把整个 JSON 文件内容塞进调试窗）
    if len(s) > 1000:
        s = s[:1000] + f"\n…（已截断，共 {len(s)} 字符）"
    return s


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
_MEMBER_START = {TeamRunEvent.task_iteration_started.value}

# 已知但不需渲染的事件（避免 debug 噪音）
_KNOWN_SILENT = {
    RunEvent.run_started.value,
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


# ─────────────────────────────────────────────────────────────
# 内容事件通用处理 — 提取 reasoning_content + <think> 标签
# ─────────────────────────────────────────────────────────────

def _dispatch_content_event(
    event: Any,
    log: _ActivityLog,
    parser: _ThinkTagParser,
    content_handler,
) -> bool:
    """处理一个 content 事件，提取思考内容并分发。

    思考内容来源（优先级）：
      1. event.reasoning_content — 模型 API 原生 reasoning（deepseek-reasoner 等）
      2. <think>...</think> in event.content — qwen3 native thinking
      3. 剩余 content — 交给 content_handler

    Returns: 是否有内容产生
    """
    has_content = False

    # 路径 1：模型 API 级别的 reasoning_content（deepseek-reasoner / o1 等）
    reasoning = getattr(event, "reasoning_content", None)
    if reasoning:
        log.on_thinking_delta(reasoning)
        has_content = True

    # 路径 2+3：解析 content 中的 <think> 标签（qwen3），剩余交给 content_handler
    content = getattr(event, "content", None)
    if content:
        chunks = parser.feed(content)
        for kind, text in chunks:
            if kind == "think":
                log.on_thinking_delta(text)
            else:
                content_handler(text)
            has_content = True

    return has_content


# ─────────────────────────────────────────────────────────────
# 流式对话核心 — 供 Gradio ChatInterface 调用
# ─────────────────────────────────────────────────────────────

async def _stream_chat(message: str, history: list) -> AsyncIterator[str]:
    """结构化活动日志异步生成器"""
    team = get_agent()
    log = _ActivityLog()
    has_yielded = False
    # 每个 content 事件源需要独立的 <think> 解析器（状态隔离）
    member_parser = _ThinkTagParser()
    team_parser = _ThinkTagParser()

    try:
        async for event in team.arun(message, stream=True, stream_events=True):
            event_type = getattr(event, "event", None)
            tool = getattr(event, "tool", None)

            if event_type in _TOOL_START:
                name = getattr(tool, "tool_name", "?") if tool else "?"
                args = getattr(tool, "tool_args", {}) or {}
                log.on_tool_start(name, args)
                has_yielded = True
                yield log.render()

            elif event_type in _TOOL_DONE:
                name = getattr(tool, "tool_name", "?") if tool else "?"
                result = getattr(tool, "result", None)
                log.on_tool_complete(name, result)
                has_yielded = True
                yield log.render()

            elif event_type in _TOOL_ERR:
                name = getattr(tool, "tool_name", "?") if tool else "?"
                error = getattr(tool, "tool_call_error", "未知错误") or "未知错误"
                log.on_tool_error(name, str(error))
                has_yielded = True
                yield log.render()

            elif event_type in _CONTENT_PLAN:
                # 主控委托前的规划文本，显示为"📋 协调"块
                content = getattr(event, "content", None)
                if content:
                    log.on_plan(content)
                    has_yielded = True
                    yield log.render()

            elif event_type in _MEMBER_INTERMEDIATE:
                # 子 Agent 工具调用之间的推理/分析文本（仅 output_model 场景）
                content = getattr(event, "content", None)
                if content:
                    log.on_thinking_delta(content)
                    has_yielded = True
                    yield log.render()

            elif event_type in _MEMBER_CONTENT:
                # 子 Agent 回复：提取 reasoning_content + <think> 标签
                if _dispatch_content_event(
                    event, log, member_parser, log.on_member_content_delta
                ):
                    has_yielded = True
                    yield log.render()

            elif event_type in _TEAM_CONTENT:
                # 主控回答：同样提取 reasoning_content + <think> 标签
                if _dispatch_content_event(
                    event, log, team_parser, log.on_answer_delta
                ):
                    has_yielded = True
                    yield log.render()

            elif event_type in _REASONING:
                # ReasoningContentDeltaEvent（独立推理事件，reasoning: true 场景）
                delta = (
                    getattr(event, "reasoning_content", None)
                    or getattr(event, "content", None)
                )
                if delta:
                    log.on_thinking_delta(delta)
                    has_yielded = True
                    yield log.render()

            elif event_type in _MEMBER_START:
                member_name = (
                    getattr(event, "member_name", None)
                    or getattr(event, "agent_name", None)
                    or getattr(event, "name", None)
                )
                if member_name:
                    # 新子 Agent 开始时，清空解析器 + 关闭前一个子 Agent 的所有开放块
                    for chunk_kind, chunk_text in member_parser.flush():
                        if chunk_kind == "think":
                            log.on_thinking_delta(chunk_text)
                        else:
                            log.on_member_content_delta(chunk_text)
                    log._close_kind("thinking")
                    log._close_kind("member_answer")
                    log._close_kind("answer")
                    log.on_member_start(member_name)
                    has_yielded = True
                    yield log.render()

            elif event_type in _ERROR:
                error_msg = getattr(event, "error", "未知错误")
                log.on_error(str(error_msg))
                has_yielded = True
                yield log.render()
                return

            elif event_type not in _KNOWN_SILENT:
                # 未知事件类型：记录 debug 日志帮助排查
                attrs = {k: v for k, v in vars(event).items()
                         if not k.startswith("_") and k != "event"}
                logger.debug("未处理事件 type=%s attrs=%s", event_type, list(attrs.keys()))

        # 流结束：清空所有 parser 缓冲区
        for chunk_kind, chunk_text in member_parser.flush():
            if chunk_kind == "think":
                log.on_thinking_delta(chunk_text)
            else:
                log.on_member_content_delta(chunk_text)
        for chunk_kind, chunk_text in team_parser.flush():
            if chunk_kind == "think":
                log.on_thinking_delta(chunk_text)
            else:
                log.on_answer_delta(chunk_text)

    except Exception as exc:
        logger.exception("_stream_chat error")
        log.on_error(str(exc))
        has_yielded = True
        yield log.render()

    # 最终渲染（含 flush 的尾部内容）
    final = log.render()
    if final:
        has_yielded = True
        yield final

    if not has_yielded:
        yield (
            "**[提示]** Team 未返回任何内容。\n\n"
            "常见原因：`configs/llm.yaml` 中 `reasoning: true` 对当前模型无效。\n"
            "qwen3 / 普通 OpenAI 兼容模型请设置 `reasoning: false`。"
        )


# ─────────────────────────────────────────────────────────────
# Gradio UI 构建
# ─────────────────────────────────────────────────────────────

def create_ui() -> gr.ChatInterface:
    return gr.ChatInterface(
        fn=_stream_chat,
        title="家宽 CEI 体验优化 Agent — 调试界面",
        description=(
            "结构化活动日志：🤖 子Agent委托 → 📋 协调规划 → 💭 思考 → 🔧 工具调用 → 💬 最终回答\n"
            "可清晰看到主控把任务委托给哪个专家、走了哪个流程、调了哪些 Skill、每步返回了什么。"
        ),
        examples=[
            "我是直播用户，晚上 8 点到 12 点需要保障上行带宽，对卡顿比较敏感",
            "帮我优化家里的网络，最近打游戏延迟很高",
            "视频会议老是卡，主要用腾讯会议，工作时间 9-18 点",
        ],
    )


if __name__ == "__main__":
    ui = create_ui()
    ui.launch(server_name="0.0.0.0", server_port=7860, share=False)
