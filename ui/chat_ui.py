"""Gradio 调试界面 — 流式对话

通过 Agno agent.run(stream=True) 实现实时流式输出，
用户在 Agent 调用 Skill、追问、生成方案过程中能看到逐步输出。

挂载路径：/gradio（由 app/main.py 通过 gr.mount_gradio_app 挂载）
独立启动：python ui/chat_ui.py（监听 7860 端口）
"""
from __future__ import annotations

from typing import Iterator

import gradio as gr

from agno.run.agent import RunEvent
from app.agent.agent import get_agent


def _stream_chat(message: str, history: list) -> Iterator[str]:
    """流式对话生成器 — 供 Gradio ChatInterface 调用

    Gradio 要求生成器 yield 累积字符串（非 delta），
    每次 yield 刷新一次界面显示。

    agent.run(stream=True) 返回 RunOutputEvent 迭代器，
    只有 RunContent 事件携带文本 delta，其余事件（ToolCall、Reasoning 等）
    透明跳过，不影响对话显示。
    """
    agent = get_agent()
    accumulated = ""

    try:
        for event in agent.run(message, stream=True):
            event_type = getattr(event, "event", None)

            if event_type == RunEvent.run_content.value:
                delta = getattr(event, "content", None)
                if delta:
                    accumulated += delta
                    yield accumulated

            elif event_type == RunEvent.run_error.value:
                error = getattr(event, "error", "未知错误")
                yield accumulated + f"\n\n[Agent 错误] {error}"
                return

    except Exception as exc:
        yield accumulated + f"\n\n[系统错误] {exc}"


def create_ui() -> gr.ChatInterface:
    """创建 Gradio ChatInterface（流式）"""
    return gr.ChatInterface(
        fn=_stream_chat,
        title="家宽体验感知优化 Agent — 调试界面",
        description=(
            "与 Agent 对话，测试意图解析、追问、方案填充、约束校验全链路。\n"
            "Agent 调用 Skill 时界面实时更新，无需等待全部完成。"
        ),
        examples=[
            "我是直播用户，晚上 8 点到 12 点需要保障上行带宽，对卡顿比较敏感",
            "帮我优化家里的网络，最近打游戏延迟很高",
            "视频会议老是卡，主要用腾讯会议，工作时间 9-18 点",
        ],
        theme=gr.themes.Soft(),
        type="messages",
    )


if __name__ == "__main__":
    ui = create_ui()
    ui.launch(server_name="0.0.0.0", server_port=7860, share=False)
