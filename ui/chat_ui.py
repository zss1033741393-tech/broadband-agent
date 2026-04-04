"""Gradio 调试界面 — 流式对话

通过 Agno agent.run(stream=True) 实现实时流式输出：
- 模型 native thinking（如 qwen3 <think> 块）在思考折叠区实时呈现
- 每次工具调用（Skill）立即显示进度提示，不再盲等
- 最终回答逐字流出

独立启动：python ui/chat_ui.py（监听 7860 端口，与 AgentOS 进程分离）
"""
from __future__ import annotations

from typing import Iterator

import gradio as gr

from agno.run.agent import RunEvent
from app.agent.agent import get_agent
from app.logger.setup import setup_logging

setup_logging()


# ─────────────────────────────────────────────────────────────
# 渲染辅助 — 将思考、工具状态、答案合并为展示字符串
# ─────────────────────────────────────────────────────────────

def _render(thinking: str, tool_hint: str, answer: str) -> str:
    """拼接最终展示内容：思考（blockquote）+ 工具状态 + 答案"""
    parts: list[str] = []

    if thinking:
        # 每行加 "> " 使其在 Markdown 里渲染为引用块
        quoted = "\n".join(f"> {line}" for line in thinking.splitlines())
        parts.append(f"**💭 思考过程**\n\n{quoted}")

    if tool_hint:
        parts.append(tool_hint)

    if answer:
        parts.append(answer)

    return "\n\n".join(parts) if parts else ""


# ─────────────────────────────────────────────────────────────
# 流式对话核心 — 供 Gradio ChatInterface 调用
# ─────────────────────────────────────────────────────────────

def _stream_chat(message: str, history: list) -> Iterator[str]:
    """流式对话生成器

    事件处理策略：
    - tool_call_started  → 立即显示"🔧 调用: tool_name…"（避免用户盲等）
    - tool_call_completed→ 清除工具状态行，避免最终回复被旧状态污染
    - run_content        → reasoning_content 追加思考区；content 追加答案区
    - run_error          → 追加错误提示

    注意：不使用 return 提前退出生成器（Gradio 异步包装层不兼容
    generator 内部 StopIteration，会抛 RuntimeError）；改用 break + 标志位。
    """
    agent = get_agent()
    thinking = ""   # 模型 native thinking 累积（qwen3 reasoning_content）
    tool_hint = ""  # 当前工具调用状态行（单行，调用完后清空）
    answer = ""     # 最终回答累积
    has_yielded = False

    try:
        for event in agent.run(message, stream=True):
            event_type = getattr(event, "event", None)

            if event_type == RunEvent.tool_call_started.value:
                tool = getattr(event, "tool", None)
                name = getattr(tool, "tool_name", "工具") if tool else "工具"
                tool_hint = f"> 🔧 调用: `{name}`…"
                has_yielded = True
                yield _render(thinking, tool_hint, answer)

            elif event_type == RunEvent.tool_call_completed.value:
                tool_hint = ""   # 工具完成，清除进度行
                has_yielded = True
                yield _render(thinking, tool_hint, answer)

            elif event_type == RunEvent.run_content.value:
                # qwen3 等原生推理模型的 thinking 块（Agno 已解析为 reasoning_content）
                reasoning_delta = getattr(event, "reasoning_content", None)
                if reasoning_delta:
                    thinking += reasoning_delta

                content_delta = getattr(event, "content", None)
                if content_delta:
                    answer += content_delta

                if reasoning_delta or content_delta:
                    has_yielded = True
                    yield _render(thinking, tool_hint, answer)

            elif event_type == RunEvent.run_error.value:
                error_msg = getattr(event, "error", "未知错误")
                answer += f"\n\n**[Agent 错误]** {error_msg}"
                has_yielded = True
                yield _render(thinking, tool_hint, answer)
                break   # 出错后停止迭代，不使用 return（避免异步上下文 StopAsyncIteration）

    except Exception as exc:
        answer += f"\n\n**[系统错误]** {exc}"
        has_yielded = True
        yield _render(thinking, tool_hint, answer)

    # 兜底：若 Agent 全程无任何输出（如 reasoning=True 解析失败）确保至少 yield 一次
    if not has_yielded:
        yield (
            "**[提示]** Agent 未返回任何内容。\n\n"
            "常见原因：`configs/llm.yaml` 中 `reasoning: true` 设置了 Agno 推理链，"
            "但当前模型（如 qwen3）不支持该模式。\n\n"
            "请将 `reasoning` 改为 `false`，仅 deepseek-reasoner / OpenAI o1/o3 才需要 true。"
        )


# ─────────────────────────────────────────────────────────────
# Gradio UI 构建
# ─────────────────────────────────────────────────────────────

def create_ui() -> gr.ChatInterface:
    """创建 Gradio ChatInterface（流式）"""
    return gr.ChatInterface(
        fn=_stream_chat,
        title="家宽体验感知优化 Agent — 调试界面",
        description=(
            "与 Agent 对话，测试意图解析、追问、方案填充、约束校验全链路。\n"
            "Agent 调用 Skill 时界面实时显示进度，无需等待全部完成。"
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
