"""Gradio 调试界面 — 使用 Agno 原生 Agent API

AgentOS 已提供完整的 REST/WS API 和 Trace 可视化，
此界面作为对话调试的轻量补充，挂载在 /gradio 路径。
"""
from __future__ import annotations

import gradio as gr

from app.agent.agent import get_agent


def create_ui() -> gr.ChatInterface:
    """创建 Gradio 调试界面"""

    def chat(message: str, history: list) -> str:
        """调用 Agno Agent，返回回复文本"""
        agent = get_agent()
        try:
            response = agent.run(message)
            if response and hasattr(response, "content") and response.content:
                return response.content
            return str(response) if response else "（无回复）"
        except Exception as exc:
            return f"[Agent 错误] {exc}"

    return gr.ChatInterface(
        fn=chat,
        title="家宽体验感知优化 Agent — 调试界面",
        description=(
            "**调试入口**：直接与 Agent 对话，测试意图解析、方案填充、约束校验全链路。\n\n"
            "生产 API 由 AgentOS 提供（`/v1/agents/.../runs`）。"
        ),
        examples=[
            "我是直播用户，晚上 8 点到 12 点需要保障上行带宽，对卡顿比较敏感",
            "帮我优化家里的网络，最近打游戏延迟很高",
            "视频会议老是卡，主要用腾讯会议，工作时间 9-18 点",
        ],
        theme=gr.themes.Soft(),
    )


if __name__ == "__main__":
    """直接运行时启动独立调试服务"""
    ui = create_ui()
    ui.launch(server_name="0.0.0.0", server_port=7860, share=False)
