"""Gradio 调试界面 — 结构化活动日志（多 Agent 架构）

每轮对话以分区块的活动日志呈现：
  🤖 子Agent — 主控委托给某个子 Agent（IntentAgent / PlanAgent / ...）
  💭 思考  — 模型 native thinking 实时流出
  🔧 工具  — 每次工具调用：工具名 + 参数（调用中 / 返回内容 / 错误）
  💬 回答  — 最终模型回复

多 Agent 事件来源：
  - RunEvent.*       — 子 Agent（IntentAgent 等）产生的事件
  - TeamRunEvent.*   — 主控 OrchestratorTeam 产生的事件
  两类事件均被捕获并统一渲染。

独立启动：python ui/chat_ui.py（监听 7860 端口，与 AgentOS 进程分离）
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import gradio as gr

from agno.run.agent import RunEvent
from agno.run.team import TeamRunEvent
from app.agent.agent import get_agent
from app.logger.setup import setup_logging

setup_logging()


# ─────────────────────────────────────────────────────────────
# 活动日志数据结构
# ─────────────────────────────────────────────────────────────

class _Section:
    """日志中的一个显示块"""
    __slots__ = ("kind", "lines", "closed")

    def __init__(self, kind: str, initial: str = ""):
        self.kind: str = kind        # "member" | "thinking" | "tool" | "answer" | "error"
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

    def on_thinking_delta(self, delta: str) -> None:
        """native thinking delta"""
        sec = self._last("thinking")
        if sec and not sec.closed:
            sec.extend_last(delta)
        else:
            self._sections.append(_Section("thinking", delta))

    def on_tool_start(self, name: str, args: dict[str, Any]) -> None:
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
        """找到最近一个未关闭的 tool section，替换"执行中"为返回内容"""
        sec = self._last_open_tool()
        if sec is None:
            return
        lines = sec.text()
        lines = lines.replace("\n\n*执行中…*", "")
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
            if sec.kind == "thinking":
                raw = sec.text()
                if raw.strip():
                    quoted = "\n".join(f"> {line}" for line in raw.splitlines())
                    parts.append(f"**💭 思考**\n\n{quoted}")
            else:
                content = sec.text()
                if content.strip():
                    parts.append(content)
        return self._SEP.join(parts) if parts else ""

    # ── 内部工具 ─────────────────────────────────────────────

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
    return str(result)


# ─────────────────────────────────────────────────────────────
# 事件类型常量集合（统一处理 RunEvent + TeamRunEvent）
# ─────────────────────────────────────────────────────────────

_TOOL_START = {RunEvent.tool_call_started.value, TeamRunEvent.tool_call_started.value}
_TOOL_DONE = {RunEvent.tool_call_completed.value, TeamRunEvent.tool_call_completed.value}
_TOOL_ERR = {RunEvent.tool_call_error.value, TeamRunEvent.tool_call_error.value}
_CONTENT = {
    RunEvent.run_content.value,
    TeamRunEvent.run_content.value,
    TeamRunEvent.run_intermediate_content.value,
}
_ERROR = {RunEvent.run_error.value, TeamRunEvent.run_error.value}
_REASONING = {RunEvent.reasoning_content_delta.value, TeamRunEvent.reasoning_content_delta.value}
_MEMBER_START = {
    TeamRunEvent.task_iteration_started.value,
}


# ─────────────────────────────────────────────────────────────
# 流式对话核心 — 供 Gradio ChatInterface 调用
# ─────────────────────────────────────────────────────────────

async def _stream_chat(message: str, history: list) -> AsyncIterator[str]:
    """结构化活动日志异步生成器

    处理来自 OrchestratorTeam 的两类事件：
    - RunEvent.*       — 子 Agent（IntentAgent 等）的工具调用 / 内容
    - TeamRunEvent.*   — 主控的工具调用 / 内容 / 子 Agent 委托
    """
    team = get_agent()
    log = _ActivityLog()
    has_yielded = False

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

            elif event_type in _CONTENT:
                reasoning = getattr(event, "reasoning_content", None)
                if reasoning:
                    log.on_thinking_delta(reasoning)

                content = getattr(event, "content", None)
                if content:
                    log.on_answer_delta(content)

                if reasoning or content:
                    has_yielded = True
                    yield log.render()

            elif event_type in _REASONING:
                delta = getattr(event, "reasoning_content", None) or getattr(event, "delta", None)
                if delta:
                    log.on_thinking_delta(delta)
                    has_yielded = True
                    yield log.render()

            elif event_type in _MEMBER_START:
                # 主控委托给子 Agent，显示切换标记
                member_name = getattr(event, "member_name", None) or getattr(event, "agent_name", None)
                if member_name:
                    log.on_member_start(member_name)
                    has_yielded = True
                    yield log.render()

            elif event_type in _ERROR:
                error_msg = getattr(event, "error", "未知错误")
                log.on_error(str(error_msg))
                has_yielded = True
                yield log.render()
                return

    except Exception as exc:
        log.on_error(str(exc))
        has_yielded = True
        yield log.render()

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
        title="家宽体验感知优化 Agent — 调试界面",
        description=(
            "结构化活动日志：🤖 子Agent委托 → 💭 思考 → 🔧 工具调用（参数+返回）→ 💬 最终回答\n"
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
