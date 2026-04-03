"""StreamEventParser 和 BroadbandAgent.run_stream() 流式管道测试

策略：
  - StreamEventParser：构造 mock Agno RunOutputEvent 对象，验证每种事件都能
    正确映射到 AgentChunk，以及无关事件返回 None。
  - BroadbandAgent.run_stream()：mock Agent.arun() 注入预设事件序列，
    收集 AgentChunk 列表，断言顺序和字段。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.agent.agent import AgentChunk, BroadbandAgent, StreamEventParser
from agno.run.agent import RunEvent


# ─────────────────────────────────────────────────────────────
# 工具函数：构造 mock Agno RunOutputEvent
# ─────────────────────────────────────────────────────────────

def _make_event(event_type: str, **kwargs) -> SimpleNamespace:
    """构造最小化的 mock RunOutputEvent，只含测试所需字段"""
    return SimpleNamespace(event=event_type, **kwargs)


def _make_tool_exec(tool_name: str, tool_args: dict, result: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        tool_name=tool_name,
        tool_args=tool_args,
        result=result,
    )


def _make_metrics(input_tokens: int = 100, output_tokens: int = 50, time_: float = 1.5) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        time=time_,
    )


# ─────────────────────────────────────────────────────────────
# StreamEventParser 单元测试
# ─────────────────────────────────────────────────────────────

class TestStreamEventParser:
    def setup_method(self) -> None:
        self.parser = StreamEventParser()

    def test_reasoning_content_delta_maps_to_reasoning_chunk(self) -> None:
        event = _make_event(RunEvent.reasoning_content_delta.value, reasoning_content="用户提到直播场景...")
        chunk = self.parser.parse(event)
        assert chunk is not None
        assert chunk.type == "reasoning_delta"
        assert chunk.delta == "用户提到直播场景..."

    def test_reasoning_content_delta_empty_returns_none(self) -> None:
        event = _make_event(RunEvent.reasoning_content_delta.value, reasoning_content="")
        assert self.parser.parse(event) is None

    def test_run_content_maps_to_content_chunk(self) -> None:
        event = _make_event(RunEvent.run_content.value, content="请问您对卡顿的敏感程度？")
        chunk = self.parser.parse(event)
        assert chunk is not None
        assert chunk.type == "content_delta"
        assert chunk.delta == "请问您对卡顿的敏感程度？"

    def test_run_content_none_returns_none(self) -> None:
        event = _make_event(RunEvent.run_content.value, content=None)
        assert self.parser.parse(event) is None

    def test_tool_call_started_maps_correctly(self) -> None:
        tool_exec = _make_tool_exec("intent_parsing", {"intent_goal_json": "{}"})
        event = _make_event(RunEvent.tool_call_started.value, tool=tool_exec)
        chunk = self.parser.parse(event)
        assert chunk is not None
        assert chunk.type == "tool_call_started"
        assert chunk.tool_name == "intent_parsing"
        assert chunk.tool_args == {"intent_goal_json": "{}"}

    def test_tool_call_completed_maps_correctly(self) -> None:
        result_json = json.dumps({"complete": False, "missing_fields": ["user_type"]})
        tool_exec = _make_tool_exec("intent_parsing", {}, result=result_json)
        event = _make_event(RunEvent.tool_call_completed.value, tool=tool_exec)
        chunk = self.parser.parse(event)
        assert chunk is not None
        assert chunk.type == "tool_call_done"
        assert chunk.tool_name == "intent_parsing"
        assert "missing_fields" in chunk.tool_result

    def test_run_completed_maps_to_done_with_metrics(self) -> None:
        metrics = _make_metrics(input_tokens=200, output_tokens=80, time_=2.3)
        event = _make_event(RunEvent.run_completed.value, metrics=metrics)
        chunk = self.parser.parse(event)
        assert chunk is not None
        assert chunk.type == "done"
        assert chunk.metrics["input_tokens"] == 200
        assert chunk.metrics["output_tokens"] == 80
        assert chunk.metrics["total_tokens"] == 280
        assert abs(chunk.metrics["time"] - 2.3) < 0.01

    def test_run_completed_no_metrics_returns_empty_dict(self) -> None:
        event = _make_event(RunEvent.run_completed.value, metrics=None)
        chunk = self.parser.parse(event)
        assert chunk is not None
        assert chunk.type == "done"
        assert chunk.metrics == {}

    def test_unknown_event_returns_none(self) -> None:
        event = _make_event("SomeUnknownEvent", content="irrelevant")
        assert self.parser.parse(event) is None

    def test_tool_call_started_no_tool_returns_none(self) -> None:
        event = _make_event(RunEvent.tool_call_started.value, tool=None)
        assert self.parser.parse(event) is None

    def test_reasoning_model_sequence(self) -> None:
        """推理模型典型事件序列：reasoning_delta × N → content_delta × N → done"""
        events = [
            _make_event(RunEvent.reasoning_content_delta.value, reasoning_content="分析用户意图"),
            _make_event(RunEvent.reasoning_content_delta.value, reasoning_content="，需要追问"),
            _make_event(RunEvent.run_content.value, content="请问您的直播应用是？"),
            _make_event(RunEvent.run_completed.value, metrics=_make_metrics()),
        ]
        chunks = [self.parser.parse(e) for e in events]
        chunks = [c for c in chunks if c is not None]

        assert chunks[0].type == "reasoning_delta"
        assert chunks[1].type == "reasoning_delta"
        assert "分析用户意图，需要追问" == chunks[0].delta + chunks[1].delta
        assert chunks[2].type == "content_delta"
        assert chunks[3].type == "done"

    def test_tool_call_sequence(self) -> None:
        """工具调用典型序列：tool_call_started → tool_call_done → content_delta → done"""
        events = [
            _make_event(RunEvent.tool_call_started.value,
                        tool=_make_tool_exec("plan_filling", {"intent_goal_json": "{}"})),
            _make_event(RunEvent.tool_call_completed.value,
                        tool=_make_tool_exec("plan_filling", {}, result='{"plans":{}}')),
            _make_event(RunEvent.run_content.value, content="方案已生成"),
            _make_event(RunEvent.run_completed.value, metrics=_make_metrics()),
        ]
        chunks = [self.parser.parse(e) for e in events]
        chunks = [c for c in chunks if c is not None]

        assert [c.type for c in chunks] == [
            "tool_call_started", "tool_call_done", "content_delta", "done"
        ]
        assert chunks[0].tool_name == "plan_filling"
        assert chunks[1].tool_name == "plan_filling"


# ─────────────────────────────────────────────────────────────
# BroadbandAgent.run_stream() 集成测试（mock Agent.arun）
# ─────────────────────────────────────────────────────────────

async def _fake_event_stream(events: list) -> AsyncIterator:
    """构造返回预设事件序列的异步迭代器"""
    for e in events:
        yield e


async def _collect_chunks(agent: BroadbandAgent, message: str) -> list[AgentChunk]:
    """收集 run_stream() 产出的所有 AgentChunk"""
    tracer = MagicMock()  # tracer.log() 等调用全部静默 no-op

    chunks: list[AgentChunk] = []
    async for chunk in agent.run_stream(message, "test-session", tracer):
        chunks.append(chunk)
    return chunks


@pytest.fixture
def agent_with_mock_llm():
    """创建 BroadbandAgent，但将内部 _agent.arun 替换为 mock"""
    with patch("app.agent.agent.Agent") as MockAgent:
        # Agent() 构造不发起网络请求
        mock_instance = MagicMock()
        MockAgent.return_value = mock_instance
        # OpenAILike 也 mock 掉
        with patch("app.agent.agent.OpenAILike"):
            agent = BroadbandAgent()
        yield agent, mock_instance


@pytest.mark.asyncio
async def test_run_stream_simple_reply(agent_with_mock_llm) -> None:
    """普通模型回复：只有 content_delta + done"""
    agent, mock_agno = agent_with_mock_llm

    fake_events = [
        _make_event(RunEvent.run_content.value, content="请问您的保障时段是？"),
        _make_event(RunEvent.run_completed.value, metrics=_make_metrics()),
    ]
    mock_agno.arun = AsyncMock(return_value=_fake_event_stream(fake_events))

    chunks = await _collect_chunks(agent, "我是直播用户")
    types = [c.type for c in chunks]
    assert types == ["content_delta", "done"]
    assert chunks[0].delta == "请问您的保障时段是？"


@pytest.mark.asyncio
async def test_run_stream_reasoning_model(agent_with_mock_llm) -> None:
    """推理模型：reasoning_delta 先于 content_delta 出现"""
    agent, mock_agno = agent_with_mock_llm

    fake_events = [
        _make_event(RunEvent.reasoning_content_delta.value, reasoning_content="用户是直播用户"),
        _make_event(RunEvent.run_content.value, content="好的，请补充保障时段"),
        _make_event(RunEvent.run_completed.value, metrics=_make_metrics()),
    ]
    mock_agno.arun = AsyncMock(return_value=_fake_event_stream(fake_events))

    chunks = await _collect_chunks(agent, "我是直播用户")
    types = [c.type for c in chunks]
    assert types == ["reasoning_delta", "content_delta", "done"]


@pytest.mark.asyncio
async def test_run_stream_with_tool_call(agent_with_mock_llm) -> None:
    """完整工具调用流程：tool_call_started → done"""
    agent, mock_agno = agent_with_mock_llm

    fake_events = [
        _make_event(RunEvent.tool_call_started.value,
                    tool=_make_tool_exec("intent_parsing", {"intent_goal_json": "{}"})),
        _make_event(RunEvent.tool_call_completed.value,
                    tool=_make_tool_exec("intent_parsing", {},
                                        result='{"complete":false,"missing_fields":["user_type"]}')),
        _make_event(RunEvent.run_content.value, content="请告诉我您的用户类型"),
        _make_event(RunEvent.run_completed.value, metrics=_make_metrics(input_tokens=300, output_tokens=50)),
    ]
    mock_agno.arun = AsyncMock(return_value=_fake_event_stream(fake_events))

    chunks = await _collect_chunks(agent, "帮我优化网络")
    types = [c.type for c in chunks]
    assert types == ["tool_call_started", "tool_call_done", "content_delta", "done"]

    skill_start = chunks[0]
    assert skill_start.tool_name == "intent_parsing"
    assert skill_start.tool_args == {"intent_goal_json": "{}"}

    skill_done = chunks[1]
    assert "missing_fields" in skill_done.tool_result

    done = chunks[-1]
    assert done.metrics["total_tokens"] == 350


@pytest.mark.asyncio
async def test_run_stream_skips_none_chunks(agent_with_mock_llm) -> None:
    """无关事件（parser 返回 None）不应出现在 chunk 序列中"""
    agent, mock_agno = agent_with_mock_llm

    fake_events = [
        _make_event("RunStarted"),                                            # 无关事件
        _make_event(RunEvent.run_content.value, content="你好"),
        _make_event("MemoryUpdateStarted"),                                   # 无关事件
        _make_event(RunEvent.run_completed.value, metrics=_make_metrics()),
    ]
    mock_agno.arun = AsyncMock(return_value=_fake_event_stream(fake_events))

    chunks = await _collect_chunks(agent, "你好")
    assert all(c is not None for c in chunks)
    assert [c.type for c in chunks] == ["content_delta", "done"]


@pytest.mark.asyncio
async def test_run_stream_propagates_exception(agent_with_mock_llm) -> None:
    """Agent 异常应向上传播，不被吞掉"""
    agent, mock_agno = agent_with_mock_llm

    async def failing_stream():
        raise RuntimeError("LLM 连接超时")
        yield  # 让 Python 识别为 async generator

    mock_agno.arun = AsyncMock(return_value=failing_stream())

    with pytest.raises(RuntimeError, match="LLM 连接超时"):
        await _collect_chunks(agent, "test")
