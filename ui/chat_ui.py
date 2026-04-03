import json
from typing import Optional

import gradio as gr

from app.agents.pipeline import PipelineState, run_pipeline
from app.logger import setup_logging

setup_logging()


async def _handle_message(
    user_message: str,
    chat_history: list,
    session_id: str,
) -> tuple[list, str, str]:
    """处理用户消息，驱动 Pipeline（async，Gradio 6 原生支持）

    Returns:
        (更新后的对话历史, session_id, 配置预览 JSON 文本)
    """
    # chat_history 格式：[{"role": "user/assistant", "content": "..."}]
    dialog_history: Optional[list[dict]] = (
        [{"role": m["role"], "content": m["content"]} for m in chat_history]
        if chat_history
        else None
    )

    state: PipelineState = await run_pipeline(
        user_input=user_message,
        user_id="demo_user",
        session_id=session_id or None,
        dialog_history=dialog_history,
    )

    if state.status == "waiting_followup":
        bot_reply = f"需要补充一些信息：\n\n{state.followup_question}"
        config_preview = "等待用户补充信息..."
    elif state.status == "done":
        intent = state.intent_goal
        intent_summary = (
            f"**意图解析**：{intent.user_type} | {intent.scenario} | "
            f"优先级 {intent.guarantee_target.priority_level}"
            if intent
            else ""
        )
        if state.output and state.output.output_files:
            files_list = "\n".join(f"- `{f}`" for f in state.output.output_files)
            bot_reply = (
                f"{intent_summary}\n\n"
                f"**Pipeline 完成！** 已生成以下配置文件：\n\n{files_list}\n\n"
                f"配置预览见右侧面板。"
            )
            config_preview = json.dumps(
                state.output.perception.model_dump(), ensure_ascii=False, indent=2
            )
        else:
            bot_reply = f"{intent_summary}\n\nPipeline 完成，但未生成配置文件（Stage4 可能已禁用）。"
            config_preview = "{}"
    elif state.status == "error":
        bot_reply = f"处理出错：{state.error_message}"
        config_preview = "{}"
    else:
        bot_reply = "正在处理..."
        config_preview = "{}"

    # Gradio 6 Chatbot 使用 messages 格式
    new_history = list(chat_history) + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": bot_reply},
    ]
    return new_history, "", state.session_id, config_preview


def build_ui() -> gr.Blocks:
    """构建 Gradio 对话调试界面（Gradio 6 兼容）"""
    # Gradio 6：theme 不再放 Blocks()，挂载到 FastAPI 时 launch() 不会被调用，
    # 所以直接在 Blocks 里用 css 或忽略主题
    with gr.Blocks(title="家宽体验感知优化 Agent") as demo:
        gr.Markdown(
            """
            # 家宽体验感知优化 Agent
            输入您的宽带体验需求，Agent 将自动生成优化方案和配置。
            """
        )

        with gr.Row():
            with gr.Column(scale=2):
                # Gradio 6 Chatbot 默认 type="messages"
                chatbot = gr.Chatbot(label="对话", height=500)
                with gr.Row():
                    msg_input = gr.Textbox(
                        label="输入",
                        placeholder="例如：我家里有直播需求，晚上 8 点到 11 点经常卡顿",
                        scale=4,
                    )
                    send_btn = gr.Button("发送", variant="primary", scale=1)

            with gr.Column(scale=1):
                config_output = gr.Code(
                    label="配置预览（感知粒度配置）",
                    language="json",
                    lines=25,
                )

        # 隐藏状态：session_id
        session_state = gr.State(value="")

        send_btn.click(
            fn=_handle_message,
            inputs=[msg_input, chatbot, session_state],
            outputs=[chatbot, msg_input, session_state, config_output],
        )
        msg_input.submit(
            fn=_handle_message,
            inputs=[msg_input, chatbot, session_state],
            outputs=[chatbot, msg_input, session_state, config_output],
        )

        gr.Examples(
            examples=[
                ["我家里有直播需求，晚上 8 点到 11 点经常卡顿，希望保障推流稳定"],
                ["我打游戏，延迟高，对延迟很敏感，每天晚上 9 点到 12 点"],
                ["家里老人看视频，稳定就行，经常断线重连"],
            ],
            inputs=msg_input,
        )

    return demo


if __name__ == "__main__":
    ui = build_ui()
    # 独立运行时才在 launch() 里传 theme
    ui.launch(server_port=7860, share=False, theme=gr.themes.Soft())
