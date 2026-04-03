"""
LLM 调用轨迹提取器

从 Agno Agent.arun() 返回的 RunResponse 中提取 LLM 请求的完整信息：
- 请求参数（model、temperature、max_tokens、is_stream）
- 请求 messages（system / user / assistant / tool）
- 响应内容（response_content）
- 推理内容（reasoning_content，用于 CoT/thinking 类模型）
- Tool 调用列表（tool_calls）
- Tool 执行结果（tool_results）
- Token 用量（tokens_in / tokens_out / tokens_reasoning）
- 耗时（latency_ms）
"""

from typing import Optional

from app.config import LLMConfig
from app.db.crud import save_llm_trace
from app.logger.logger import get_logger

_logger = get_logger("Tracer", "LLMTracer")


def _extract_messages(response) -> tuple[list[dict], str, str, list[dict], list[dict]]:
    """从 RunResponse.messages 中拆分请求消息和响应内容

    Returns:
        (request_messages, response_content, reasoning_content, tool_calls, tool_results)
    """
    request_messages: list[dict] = []
    response_content: str = ""
    reasoning_content: str = ""
    tool_calls: list[dict] = []
    tool_results: list[dict] = []

    messages = getattr(response, "messages", None) or []

    for msg in messages:
        role = getattr(msg, "role", "") or ""
        # content 可能是字符串或列表（multimodal）
        raw_content = getattr(msg, "content", None)
        content_str = _normalize_content(raw_content)

        if role in ("system", "user"):
            request_messages.append({"role": role, "content": content_str})

        elif role == "assistant":
            # 最终回复文本
            if content_str:
                response_content = content_str

            # 推理内容：不同模型字段名不同
            for attr in ("reasoning_content", "thinking", "reasoning"):
                val = getattr(msg, attr, None)
                if val:
                    reasoning_content = str(val)
                    break

            # Tool 调用：assistant 消息中的 tool_calls 字段
            tc_list = getattr(msg, "tool_calls", None) or []
            for tc in tc_list:
                try:
                    func = getattr(tc, "function", None)
                    tool_calls.append({
                        "id": getattr(tc, "id", ""),
                        "name": func.name if func else getattr(tc, "name", ""),
                        "arguments": func.arguments if func else getattr(tc, "arguments", ""),
                    })
                except Exception:
                    pass

        elif role == "tool":
            # Tool 执行结果消息
            tool_results.append({
                "tool_call_id": getattr(msg, "tool_call_id", ""),
                "name": getattr(msg, "name", ""),
                "content": content_str,
            })

    # fallback：messages 为空时直接取 response.content
    if not response_content:
        raw = getattr(response, "content", None)
        response_content = _normalize_content(raw)

    return request_messages, response_content, reasoning_content, tool_calls, tool_results


def _extract_usage(response) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """从 RunResponse 中提取 token 用量

    Returns:
        (tokens_in, tokens_out, tokens_reasoning)
    """
    tokens_in = tokens_out = tokens_reasoning = None

    # Agno RunResponse.metrics 是一个 dict
    metrics = getattr(response, "metrics", None) or {}
    if isinstance(metrics, dict):
        pt = metrics.get("prompt_tokens")
        tokens_in = (
            metrics.get("input_tokens")
            or (pt[0] if isinstance(pt, list) else pt)
        )
        tokens_out = metrics.get("output_tokens") or metrics.get("completion_tokens")
        tokens_reasoning = metrics.get("reasoning_tokens")

    # 部分版本挂在 response.usage 上（OpenAI SDK 原生格式）
    usage = getattr(response, "usage", None)
    if usage and tokens_in is None:
        tokens_in = getattr(usage, "prompt_tokens", None)
        tokens_out = getattr(usage, "completion_tokens", None)
        completion_details = getattr(usage, "completion_tokens_details", None)
        if completion_details:
            tokens_reasoning = getattr(completion_details, "reasoning_tokens", None)

    return tokens_in, tokens_out, tokens_reasoning


def _normalize_content(raw) -> str:
    """将各种 content 类型统一为字符串"""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        # multimodal：取所有 text 部分拼接
        parts = []
        for item in raw:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(raw)


async def record_llm_trace(
    session_id: str,
    stage: str,
    component: str,
    llm_cfg: LLMConfig,
    response,
    latency_ms: float,
    is_stream: bool = False,
) -> None:
    """从 Agno RunResponse 提取 LLM 调用完整信息并持久化到 llm_traces 表

    调用时机：每次 agent.arun() / agent.run() 完成后立即调用。
    出错时记录警告，不阻断主流程。

    Args:
        session_id: 会话 ID
        stage: Pipeline 阶段，如 "Stage1"
        component: Agent 组件名，如 "IntentParser"
        llm_cfg: 当前 Stage 的 LLMConfig（提供 model/temperature/max_tokens）
        response: agno Agent.arun() 返回的 RunResponse 对象
        latency_ms: 本次 arun() 的耗时（毫秒）
        is_stream: 是否流式调用
    """
    try:
        (
            request_messages,
            response_content,
            reasoning_content,
            tool_calls,
            tool_results,
        ) = _extract_messages(response)

        tokens_in, tokens_out, tokens_reasoning = _extract_usage(response)

        await save_llm_trace(
            session_id=session_id,
            stage=stage,
            component=component,
            model=llm_cfg.model,
            temperature=llm_cfg.temperature,
            max_tokens=llm_cfg.max_tokens,
            is_stream=is_stream,
            request_messages=request_messages,
            response_content=response_content,
            reasoning_content=reasoning_content or None,
            tool_calls=tool_calls or None,
            tool_results=tool_results or None,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_reasoning=tokens_reasoning,
            latency_ms=latency_ms,
        )

        _logger.debug(
            f"LLM 轨迹已记录 | stage={stage} | model={llm_cfg.model} "
            f"| msgs={len(request_messages)} | tool_calls={len(tool_calls)} "
            f"| tokens_in={tokens_in} | tokens_out={tokens_out} "
            f"| latency_ms={latency_ms:.0f}"
        )

    except Exception as e:
        _logger.warning(f"LLM 轨迹记录失败（不影响主流程） | error={e}")
