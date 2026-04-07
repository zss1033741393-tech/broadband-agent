"""折叠思考/工具调用的消息渲染逻辑。

将 agno 的流式事件映射为 Gradio ChatMessage 格式。
"""

from typing import Any, Dict, List, Optional


def render_thinking(content: str) -> Dict[str, Any]:
    """渲染思考过程为折叠块。"""
    return {
        "role": "assistant",
        "metadata": {"title": "💭 思考"},
        "content": content,
    }


def render_tool_call(skill_name: str, inputs: Any = None, outputs: Any = None) -> Dict[str, Any]:
    """渲染工具调用为折叠块。"""
    parts = []
    if inputs is not None:
        parts.append(f"**输入参数**:\n```json\n{_format_json(inputs)}\n```")
    if outputs is not None:
        parts.append(f"**返回结果**:\n```json\n{_format_json(outputs)}\n```")
    content = "\n\n".join(parts) if parts else "调用中..."

    return {
        "role": "assistant",
        "metadata": {"title": f"🔧 调用 {skill_name}"},
        "content": content,
    }


def render_response(content: str) -> Dict[str, Any]:
    """渲染最终回答。"""
    return {
        "role": "assistant",
        "content": content,
    }


def _format_json(data: Any) -> str:
    """将数据格式化为 JSON 字符串。"""
    import json
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return str(data)
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(data)
