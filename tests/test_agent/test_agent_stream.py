"""Agent 流式输出测试

策略：
  - mock Agent.arun() 注入预设事件序列，验证 Agno 原生流式事件可正确处理。
  - 测试 Agent 初始化是否正确注册 Skills + tools + Guardrails。
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agno.run.agent import RunEvent


# ─────────────────────────────────────────────────────────────
# 工具函数：构造 mock RunOutputEvent
# ─────────────────────────────────────────────────────────────

def _make_event(event_type: str, **kwargs) -> SimpleNamespace:
    return SimpleNamespace(event=event_type, **kwargs)


def _make_tool_exec(tool_name: str, tool_args: dict, result: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(tool_name=tool_name, tool_args=tool_args, result=result)


def _make_metrics(input_tokens: int = 100, output_tokens: int = 50, time_: float = 1.5) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        time=time_,
    )


# ─────────────────────────────────────────────────────────────
# Agent 初始化测试（mock LLM 和 Skills）
# ─────────────────────────────────────────────────────────────

class TestAgentInit:
    """验证 Agent 初始化正确注册 Skills + tools"""

    def test_agent_builds_without_network(self) -> None:
        """构建 Agent 不应发起网络请求"""
        with patch("app.agent.agent.Agent") as MockAgent, \
             patch("app.agent.agent.OpenAILike"), \
             patch("app.agent.agent._discover_skills") as mock_discover, \
             patch("app.agent.agent._build_knowledge", return_value=None):

            mock_discover.return_value = MagicMock()
            MockAgent.return_value = MagicMock()
            from app.agent.agent import build_agent
            agent = build_agent()
            assert MockAgent.called

    def test_agno_tools_registered(self) -> None:
        """build_agno_tools 应返回非空 tool 列表"""
        with patch("app.agent.agent.Agent"), \
             patch("app.agent.agent.OpenAILike"), \
             patch("app.agent.agent._build_knowledge", return_value=None):
            from app.agent.agent import _build_agno_tools
            tools = _build_agno_tools()
            assert len(tools) > 0
            tool_names = {t.name for t in tools}
            assert "intent_parsing" in tool_names
            assert "constraint_check" in tool_names

    def test_skills_discovery(self) -> None:
        """_discover_skills 应返回 Skills 对象"""
        from agno.skills import Skills
        from app.agent.agent import _discover_skills
        skills = _discover_skills()
        assert isinstance(skills, Skills)


# ─────────────────────────────────────────────────────────────
# 流式事件处理测试（mock arun）
# ─────────────────────────────────────────────────────────────

async def _fake_stream(events: list) -> AsyncIterator:
    for e in events:
        yield e


async def _collect_stream(mock_agent, message: str) -> list:
    """收集 agent.arun() 产出的所有事件"""
    chunks = []
    stream = await mock_agent.arun(message, stream=True, stream_events=True)
    async for event in stream:
        chunks.append(event)
    return chunks


@pytest.fixture
def mock_agent():
    """创建 mock Agno Agent"""
    with patch("app.agent.agent.Agent") as MockAgent, \
         patch("app.agent.agent.OpenAILike"), \
         patch("app.agent.agent._discover_skills") as mock_discover, \
         patch("app.agent.agent._build_knowledge", return_value=None):
        mock_discover.return_value = MagicMock()
        instance = MagicMock()
        MockAgent.return_value = instance
        yield instance


@pytest.mark.asyncio
async def test_stream_content_event(mock_agent) -> None:
    """content 事件应被 arun 流正确产出"""
    fake_events = [
        _make_event(RunEvent.run_content.value, content="请问您的保障时段是？"),
        _make_event(RunEvent.run_completed.value, metrics=_make_metrics()),
    ]
    mock_agent.arun = AsyncMock(return_value=_fake_stream(fake_events))

    chunks = await _collect_stream(mock_agent, "我是直播用户")
    assert len(chunks) == 2
    assert chunks[0].content == "请问您的保障时段是？"


@pytest.mark.asyncio
async def test_stream_tool_call_events(mock_agent) -> None:
    """tool_call 事件序列应完整传递"""
    fake_events = [
        _make_event(RunEvent.tool_call_started.value,
                    tool=_make_tool_exec("intent_parsing", {"intent_goal_json": "{}"})),
        _make_event(RunEvent.tool_call_completed.value,
                    tool=_make_tool_exec("intent_parsing", {},
                                         result='{"complete":false,"missing_fields":["user_type"]}')),
        _make_event(RunEvent.run_content.value, content="请告诉我您的用户类型"),
        _make_event(RunEvent.run_completed.value, metrics=_make_metrics(input_tokens=300, output_tokens=50)),
    ]
    mock_agent.arun = AsyncMock(return_value=_fake_stream(fake_events))

    chunks = await _collect_stream(mock_agent, "帮我优化网络")
    event_types = [c.event for c in chunks]
    assert RunEvent.tool_call_started.value in event_types
    assert RunEvent.tool_call_completed.value in event_types
    assert RunEvent.run_content.value in event_types


@pytest.mark.asyncio
async def test_stream_reasoning_events(mock_agent) -> None:
    """推理模型 reasoning_content_delta 事件应被完整传递"""
    fake_events = [
        _make_event(RunEvent.reasoning_content_delta.value, reasoning_content="用户是直播用户"),
        _make_event(RunEvent.run_content.value, content="好的，请补充保障时段"),
        _make_event(RunEvent.run_completed.value, metrics=_make_metrics()),
    ]
    mock_agent.arun = AsyncMock(return_value=_fake_stream(fake_events))

    chunks = await _collect_stream(mock_agent, "我是直播用户")
    event_types = [c.event for c in chunks]
    assert RunEvent.reasoning_content_delta.value in event_types


@pytest.mark.asyncio
async def test_stream_propagates_exception(mock_agent) -> None:
    """Agent 异常应向上传播，不被吞掉"""
    async def failing_stream():
        raise RuntimeError("LLM 连接超时")
        yield

    mock_agent.arun = AsyncMock(return_value=failing_stream())

    with pytest.raises(RuntimeError, match="LLM 连接超时"):
        await _collect_stream(mock_agent, "test")
