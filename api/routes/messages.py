"""GET /api/conversations/:id/messages（历史查询）
POST /api/conversations/:id/messages（SSE 流式响应）
"""

from __future__ import annotations

import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from api import repository as repo
from api.agent_bridge import get_session_context
from api.engine_config import get_config
from api.event_adapter import MessageAggregate, adapt
from api.models import (
    ApiResponse,
    MessageListData,
    SendMessageRequest,
    err,
    ok,
)

router = APIRouter(prefix="/conversations/{conv_id}/messages", tags=["messages"])

_api_log = logger.bind(channel="api")


@router.get("", response_model=ApiResponse)
async def list_messages(conv_id: str):
    conv = await repo.get_conversation(conv_id)
    if conv is None:
        _api_log.warning(f"list_messages: 会话不存在 conv_id={conv_id}")
        return err(1002, "会话不存在")
    msgs = await repo.list_messages(conv_id)
    _api_log.bind(conv_id=conv_id).info(f"list_messages → {len(msgs)} 条")
    return ok(MessageListData(list=msgs))


@router.post("")
async def send_message(conv_id: str, body: SendMessageRequest):
    conv = await repo.get_conversation(conv_id)
    if conv is None:
        _api_log.warning(f"send_message: 会话不存在 conv_id={conv_id}")
        raise HTTPException(status_code=404, detail="会话不存在")

    # 先落业务库（api.db）的用户消息（前端历史回放用）
    await repo.insert_user_message(conv_id, body.content)
    _api_log.bind(conv_id=conv_id).info(
        f"send_message ← user_content_len={len(body.content)} preview={body.content[:80]!r}"
    )

    engine_cfg = get_config()

    if engine_cfg["engine"] == "opencode":
        # ── OpenCode 通道 ──
        from api.opencode_adapter import adapt_opencode
        from api.opencode_bridge import OpenCodeClient

        oc = OpenCodeClient(base_url=engine_cfg["opencode_url"])
        # Bug5 fix: 提前创建/获取 session，把 sid 直接传给 adapt_opencode，
        # 消除 main_session_id 从首条事件推断的竞态风险。
        # ensure_session 内部有缓存（_session_map），后续 send_and_stream 二次调用无额外 HTTP。
        oc_sid = await oc.ensure_session(conv_id)
        raw_stream = oc.send_and_stream(
            conv_id,
            body.content,
            agent=engine_cfg.get("opencode_agent", "orchestrator"),
        )
        adapter_factory = lambda: adapt_opencode(conv_id, raw_stream, session_id=oc_sid)  # noqa: E731
    else:
        # ── agno 通道（现有逻辑不变）──
        # 取 SessionContext（含 team / tracer / observability DB session_id）
        ctx = get_session_context(conv_id)

        # 在 observability 库（sessions.db）落 user 消息
        user_msg_id = None
        try:
            ctx.tracer.request(body.content)
            if ctx.db_session_id:
                from core.observability.db import db as _obs_db

                user_msg_id = _obs_db.insert_message(ctx.db_session_id, "user", body.content)
        except Exception:
            _api_log.exception("observability 入库 user 消息失败（不影响主流程）")

        agno_raw_stream = ctx.team.arun(
            body.content,
            session_id=conv_id,
            stream=True,
            stream_events=True,
        )
        adapter_factory = lambda: adapt(  # noqa: E731
            conv_id,
            agno_raw_stream,
            tracer=ctx.tracer,
            db_session_id=ctx.db_session_id,
            user_msg_id=user_msg_id,
        )

    # 包装成 SSE 生成器，完成后落库 assistant 消息
    async def sse_generator() -> AsyncGenerator[str, None]:
        agg: MessageAggregate | None = None
        adapter = adapter_factory()
        started_at = time.monotonic()
        chunk_count = 0
        # logger.bind() 替代 logger.contextualize()：
        # contextualize() 用 ContextVar.reset() 清理，在 Windows asyncio 下 GeneratorExit
        # 会在不同 Task Context 触发，导致 "Token was created in a different Context" ValueError。
        # bind() 返回绑定字段的 logger 实例，无 ContextVar，天然规避跨 Task 清理问题。
        _sse_log = _api_log.bind(conv_id=conv_id)
        try:
            async for chunk, current_agg in adapter:
                agg = current_agg
                chunk_count += 1
                yield chunk
        except Exception as exc:
            _sse_log.exception("SSE 生成异常")
            from api.sse import format_sse

            yield format_sse("error", {"message": f"服务器内部错误：{exc}"})

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        msg_id = agg.message_id if agg else "-"
        status = agg.status if agg else "unknown"
        _sse_log.bind(msg_id=msg_id).info(
            f"send_message → SSE 流结束 chunks={chunk_count} "
            f"elapsed_ms={elapsed_ms} status={status}"
        )

        # 落库 assistant 消息
        if agg is not None:
            try:
                steps_data = []
                for s in agg.steps:
                    # 流结束时 flush 未被 ToolCallStarted 消费的残留缓冲
                    # （最后一个 Skill 完成后 InsightAgent 可能还有反思/总结文本和 thinking）
                    items = list(s.items)
                    if s.pending_text:
                        items.append({"type": "text", "content": s.pending_text})
                    if s.pending_thinking:
                        items.append(
                            {
                                "type": "thinking",
                                "content": s.pending_thinking,
                                "startedAt": 0,
                                "endedAt": 0,
                            }
                        )
                    steps_data.append(
                        {
                            "stepId": s.step_id,
                            "title": s.title,
                            "items": items,
                            "subSteps": s.sub_steps,  # 保留，供旧前端降级 / 计数
                            "textContent": s.text_content,
                        }
                    )
                await repo.insert_assistant_message(
                    conv_id=conv_id,
                    content=agg.content,
                    thinking_content=agg.thinking_content,
                    thinking_duration_sec=agg.thinking_duration_sec,
                    steps=steps_data,
                    render_blocks=agg.render_blocks,
                    status=agg.status,
                    input_tokens=agg.input_tokens,
                    output_tokens=agg.output_tokens,
                    total_tokens=agg.total_tokens,
                    reasoning_tokens=agg.reasoning_tokens,
                )
                _api_log.bind(conv_id=conv_id, msg_id=agg.message_id).info(
                    f"assistant 消息已落库 content_len={len(agg.content)} "
                    f"steps={len(steps_data)} renders={len(agg.render_blocks)}"
                )
            except Exception:
                _api_log.exception("assistant 消息落库失败")

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
