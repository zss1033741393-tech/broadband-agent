"""OpenCode Server 与 API 层之间的接缝。

等价于 agent_bridge.py 对 agno 的封装，
但底层调用 OpenCode 的 HTTP API（opencode serve）。
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import httpx
from loguru import logger

_log = logger.bind(channel="opencode")

_session_map: dict[str, str] = {}


class OpenCodeClient:
    """封装对 opencode serve 的 HTTP 调用。"""

    def __init__(self, base_url: str = "http://127.0.0.1:4096") -> None:
        self.base_url = base_url.rstrip("/")

    async def health(self) -> bool:
        """检查 OpenCode Server 是否在线。

        用 GET /session 探活（返回任意非 5xx 状态码即视为在线）。
        /global/health 在部分 OpenCode 版本中不存在，故不用它。
        """
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{self.base_url}/session")
                return r.status_code < 500
        except Exception:
            return False

    async def ensure_session(self, conv_id: str) -> str:
        """获取或创建 OpenCode session，返回 session_id。"""
        if conv_id in _session_map:
            return _session_map[conv_id]

        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(
                    f"{self.base_url}/session",
                    json={"title": f"broadband-{conv_id[:8]}"},
                )
                r.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.text[:300]
            except Exception:
                pass
            raise RuntimeError(
                f"OpenCode Server 返回 {e.response.status_code}，session 创建失败"
                + (f"（{body}）" if body else "")
                + "。请检查：① opencode serve 是否在项目根目录启动；"
                "② opencode.json 中 LLM provider 配置是否正确"
            ) from e
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise RuntimeError(
                f"无法连接到 OpenCode Server（{self.base_url}），请先执行：opencode serve --port 4096"
            ) from e

        session = r.json()
        sid = session["id"]
        _session_map[conv_id] = sid
        _log.info(f"OpenCode session 创建: conv_id={conv_id} → sid={sid}")
        return sid

    async def send_and_stream(
        self,
        conv_id: str,
        message: str,
        agent: str = "orchestrator",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """发送消息并消费 SSE 事件流。

        流程：
        1. 预检 OpenCode Server 是否在线
        2. POST /session/:id/prompt_async 异步发送
        3. GET /event 监听全局 SSE，过滤该 session 的事件
        4. 直到收到 session.idle（该 session 的消息处理完毕）

        Yields:
            OpenCode 原始事件 dict（type + properties）
        """
        sid = await self.ensure_session(conv_id)

        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(
                f"{self.base_url}/session/{sid}/prompt_async",
                json={
                    "agent": agent,
                    "parts": [{"type": "text", "text": message}],
                },
            )
        _log.info(f"消息已发送 conv_id={conv_id} sid={sid}")

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as c:
            async with c.stream("GET", f"{self.base_url}/event") as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        continue
                    if not line.startswith("data:"):
                        continue

                    try:
                        raw = json.loads(line[5:])
                    except json.JSONDecodeError:
                        continue

                    event = raw.get("payload", raw)
                    props = event.get("properties", {})

                    event_session = (
                        props.get("sessionID")
                        or props.get("info", {}).get("sessionID")
                        or (props.get("part", {}) or {}).get("sessionID")
                    )
                    if event_session and event_session != sid:
                        continue

                    yield event

                    if event.get("type") == "session.idle":
                        if props.get("sessionID") == sid:
                            return
