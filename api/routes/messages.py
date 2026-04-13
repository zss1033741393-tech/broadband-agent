"""GET /api/conversations/:id/messages（历史查询）
POST /api/conversations/:id/messages（SSE 流式响应）
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from api.models import (
    ApiResponse,
    MessageListData,
    SendMessageRequest,
    ok,
    err,
)
from api import repository as repo
from api.agent_bridge import get_event_stream
from api.event_adapter import adapt, MessageAggregate

_SSE_LOGS_DIR = Path(__file__).resolve().parents[2] / "data" / "sse_logs"
_SSE_LOGS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/conversations/{conv_id}/messages", tags=["messages"])


@router.get("", response_model=ApiResponse)
async def list_messages(conv_id: str):
    conv = await repo.get_conversation(conv_id)
    if conv is None:
        return err(1002, "会话不存在")
    msgs = await repo.list_messages(conv_id)
    return ok(MessageListData(list=msgs))


@router.post("")
async def send_message(conv_id: str, body: SendMessageRequest):
    conv = await repo.get_conversation(conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 先落库用户消息
    await repo.insert_user_message(conv_id, body.content)

    # 启动 agno 流
    raw_stream = await get_event_stream(conv_id, body.content)

    # 包装成 SSE 生成器，完成后落库 assistant 消息
    async def sse_generator() -> AsyncGenerator[str, None]:
        agg: MessageAggregate | None = None
        event_log: list[dict] = []
        adapter = adapt(conv_id, raw_stream)
        try:
            async for chunk, current_agg in adapter:
                agg = current_agg
                # 解析本帧事件类型和数据，追加到日志
                try:
                    lines = chunk.strip().splitlines()
                    evt = next((l[7:] for l in lines if l.startswith("event: ")), "")
                    raw = next((l[6:] for l in lines if l.startswith("data: ")), "{}")
                    event_log.append({"event": evt, "data": json.loads(raw)})
                except Exception:
                    pass
                yield chunk
        except Exception as exc:
            logger.exception("SSE 生成异常")
            from api.sse import format_sse
            yield format_sse("error", {"message": f"服务器内部错误：{exc}"})

        # 写 SSE 事件日志
        if event_log:
            try:
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                log_path = _SSE_LOGS_DIR / f"{conv_id}_{ts}.json"
                log_path.write_text(
                    json.dumps(event_log, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                logger.exception("SSE 日志写入失败")

        # 落库 assistant 消息
        if agg is not None:
            try:
                steps_data = [
                    {
                        "stepId": s.step_id,
                        "title": s.title,
                        "subSteps": s.sub_steps,
                    }
                    for s in agg.steps
                ]
                await repo.insert_assistant_message(
                    conv_id=conv_id,
                    content=agg.content,
                    thinking_content=agg.thinking_content,
                    thinking_duration_sec=agg.thinking_duration_sec,
                    steps=steps_data,
                    render_blocks=agg.render_blocks,
                    status=agg.status,
                )
            except Exception:
                logger.exception("assistant 消息落库失败")

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
