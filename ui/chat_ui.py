"""Gradio 对话调试界面 — 三栏布局：对话区 / 输出物面板 / Trace 面板"""
import json
import zipfile
from pathlib import Path
from typing import Any

import gradio as gr

from app.agent.agent import BroadbandAgent
from app.agent.tracer import AgentTracer


def _scan_artifacts(artifacts_dir: Path) -> dict[str, Any]:
    """扫描 artifacts/ 目录，返回已生成输出物的结构"""
    result: dict[str, Any] = {}
    if not artifacts_dir.exists():
        return result
    for f in sorted(artifacts_dir.rglob("*.json")):
        try:
            content = json.loads(f.read_text(encoding="utf-8"))
            rel = str(f.relative_to(artifacts_dir))
            result[rel] = content
        except Exception:
            pass
    return result


def _make_zip(trace_dir: Path) -> str:
    """打包整个 session 目录为 zip，返回 zip 文件路径"""
    zip_path = str(trace_dir) + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in trace_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(trace_dir.parent))
    return zip_path


def create_ui(agent: BroadbandAgent) -> gr.Blocks:
    """创建 Gradio 调试界面"""

    async def chat_handler(
        message: str,
        history: list[dict[str, str]],
        session_state: dict | None,
    ) -> tuple:
        """处理用户消息，返回更新后的各面板内容"""
        if not message.strip():
            yield history, {}, "", [], _status_bar(session_state), session_state
            return

        # 初始化或恢复 tracer
        if session_state is None:
            tracer = AgentTracer()
            session_state = {"session_id": tracer.session_id, "_tracer": tracer}
        else:
            tracer = session_state["_tracer"]

        # 调用 Agent
        result = await agent.run(message, history, tracer)

        # 更新对话历史
        updated_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": result["content"]},
        ]

        # 保存对话记录
        tracer.save_conversation(updated_history)

        # 思考过程 Markdown
        thinking_md = ""
        if result["thinking"]:
            skill = result["skill_used"]
            thinking_md = (
                f"**Step {tracer.step}**"
                + (f" — `{skill}`" if skill else "")
                + f"\n\n{result['thinking']}"
            )

        # 读取 artifacts
        artifacts = _scan_artifacts(tracer.trace_dir / "artifacts")

        # 读取 trace 摘要
        trace_rows = tracer.read_trace_summary()

        # 状态栏
        status = _status_bar(session_state)

        yield updated_history, artifacts, thinking_md, trace_rows, status, session_state

    def _status_bar(state: dict | None) -> str:
        if state is None:
            return "Session: - │ Steps: 0 │ Skills: 0 │ Duration: 0s"
        tracer: AgentTracer = state["_tracer"]
        return (
            f"Session: `{tracer.session_id}` │ "
            f"Steps: {tracer.step} │ "
            f"Skills: {len(tracer.skills_used)} │ "
            f"Duration: {tracer.elapsed()}s"
        )

    def export_trace(session_state: dict | None) -> str | None:
        """导出完整轨迹为 zip"""
        if session_state is None:
            return None
        tracer: AgentTracer = session_state["_tracer"]
        return _make_zip(tracer.trace_dir)

    with gr.Blocks(
        title="家宽体验感知优化 Agent",
        theme=gr.themes.Soft(),
    ) as app:
        gr.Markdown("# 家宽体验感知优化 Agent")

        session_state = gr.State(value=None)

        with gr.Row():
            # 左列：对话区
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="对话",
                    type="messages",
                    show_copy_button=True,
                    height=520,
                    bubble_full_width=False,
                )
                with gr.Row():
                    msg_input = gr.Textbox(
                        placeholder="描述您的保障需求，例如：我是直播用户，晚上 7-11 点需要保障上行带宽...",
                        show_label=False,
                        scale=5,
                    )
                    send_btn = gr.Button("发送", variant="primary", scale=1)

                with gr.Accordion("🧠 Agent 思考过程", open=False):
                    thinking_display = gr.Markdown(value="（暂无）")

            # 右列：输出物 + Trace
            with gr.Column(scale=2):
                with gr.Accordion("📊 阶段输出物", open=True):
                    artifacts_display = gr.JSON(
                        label="当前输出物",
                        height=300,
                    )

                with gr.Accordion("🔍 Agent Trace", open=True):
                    trace_display = gr.Dataframe(
                        headers=["Step", "Type", "Skill", "Summary"],
                        label="轨迹记录",
                        height=200,
                        interactive=False,
                    )
                    export_btn = gr.Button("📤 导出完整轨迹（zip）", size="sm")
                    export_file = gr.File(label="下载轨迹", visible=False)

        # 底部状态栏
        status_bar = gr.Markdown("Session: - │ Steps: 0 │ Skills: 0 │ Duration: 0s")

        # 事件绑定
        submit_inputs = [msg_input, chatbot, session_state]
        submit_outputs = [
            chatbot,
            artifacts_display,
            thinking_display,
            trace_display,
            status_bar,
            session_state,
        ]

        msg_input.submit(
            fn=chat_handler,
            inputs=submit_inputs,
            outputs=submit_outputs,
        ).then(lambda: "", outputs=msg_input)

        send_btn.click(
            fn=chat_handler,
            inputs=submit_inputs,
            outputs=submit_outputs,
        ).then(lambda: "", outputs=msg_input)

        export_btn.click(
            fn=export_trace,
            inputs=[session_state],
            outputs=[export_file],
        ).then(lambda: gr.File(visible=True), outputs=[export_file])

    return app


if __name__ == "__main__":
    # 直接运行时启动独立 Gradio 服务（开发调试用）
    from app.agent.agent import BroadbandAgent

    agent = BroadbandAgent()
    ui = create_ui(agent)
    ui.launch(server_name="0.0.0.0", server_port=7860, share=False)
