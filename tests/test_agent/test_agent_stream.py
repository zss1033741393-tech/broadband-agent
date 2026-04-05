"""Agent 初始化与 Agno 流式事件测试

策略：
  - mock OpenAIChat + Skills 避免网络请求
  - 验证 discover_skills / build_knowledge / Agent 构建正确
  - 验证 Agno 原生 arun() 流式事件可正确迭代
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


async def _fake_stream(events: list) -> AsyncIterator:
    for e in events:
        yield e


async def _collect_stream(mock_agent, message: str) -> list:
    chunks = []
    stream = await mock_agent.arun(message, stream=True, stream_events=True)
    async for event in stream:
        chunks.append(event)
    return chunks


# ─────────────────────────────────────────────────────────────
# Agent 初始化测试
# ─────────────────────────────────────────────────────────────

class TestAgentInit:

    def test_discover_skills_returns_skills_object(self) -> None:
        """discover_skills 应返回 Agno Skills 实例"""
        from agno.skills import Skills
        from app.agent.agent import discover_skills, SKILLS_DIR
        skills = discover_skills(SKILLS_DIR)
        assert isinstance(skills, Skills)

    def test_discover_skills_finds_all_skill_dirs(self) -> None:
        """discover_skills 应发现所有含 SKILL.md 的子目录"""
        from app.agent.agent import discover_skills, SKILLS_DIR
        skills = discover_skills(SKILLS_DIR)
        names = skills.get_skill_names()
        for expected in ["intent_parser", "user_profiler", "plan_generator",
                         "constraint_checker", "config_translator", "domain_expert"]:
            assert expected in names, f"Skill '{expected}' 未被发现"

    def test_skills_provide_meta_tools(self) -> None:
        """Skills 应自动注入元工具 get_skill_instructions / get_skill_script"""
        from app.agent.agent import discover_skills, SKILLS_DIR
        skills = discover_skills(SKILLS_DIR)
        tool_names = {t.name for t in skills.get_tools()}
        assert "get_skill_instructions" in tool_names
        assert "get_skill_script" in tool_names
        assert "get_skill_reference" in tool_names

    def test_agent_has_no_hardcoded_tools(self) -> None:
        """agent.py 不应有手写的 _build_agno_tools 或 tools= 注册"""
        import app.agent.agent as agent_module
        assert not hasattr(agent_module, "_build_agno_tools"), \
            "_build_agno_tools 不应存在，技能通过 LocalSkills 元工具原生执行"

    def test_agent_uses_openai_chat(self) -> None:
        """LLM 模型应使用 OpenAIChat（openai provider），不用 OpenAILike 作为模型类"""
        import app.agent.agent as agent_module
        import inspect
        src = inspect.getsource(agent_module._build_model)
        assert "OpenAIChat" in src, "openai provider 应使用 OpenAIChat"
        assert "OpenAILike" not in src, "模型层不应使用 OpenAILike（嵌入器层另行处理）"

    def test_system_prompt_no_hardcoded_skill_names(self) -> None:
        """SYSTEM_PROMPT 不应硬编码具体技能名（如 intent_parser）"""
        from app.agent.agent import SYSTEM_PROMPT
        # 技能名列表由 <skills_system> 动态注入，prompt 只描述流程
        hardcoded = [
            "intent_parser:", "user_profiler:", "plan_generator:",
            "constraint_checker:", "config_translator:", "domain_expert:",
        ]
        for name in hardcoded:
            assert name not in SYSTEM_PROMPT, \
                f"SYSTEM_PROMPT 硬编码了技能名 '{name}'，应由 <skills_system> 动态注入"

    def test_build_agent_without_network(self) -> None:
        """build_agent（多 Agent 架构）不应发起网络请求，返回 Team 实例"""
        with patch("app.agent.team.Team") as MockTeam, \
             patch("app.agent.team.OpenAIChat"):
            MockTeam.return_value = MagicMock()
            from app.agent.agent import build_agent
            agent = build_agent()
            assert MockTeam.called
            # 验证 tool_call_limit 被传入（对应设计文档的 max_turns 概念）
            call_kwargs = MockTeam.call_args[1]
            assert "tool_call_limit" in call_kwargs


# ─────────────────────────────────────────────────────────────
# Agno 原生流式事件测试
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_agno_agent():
    instance = MagicMock()
    return instance


@pytest.mark.asyncio
async def test_stream_content_event(mock_agno_agent) -> None:
    """content 事件应被 arun() 流正确产出"""
    fake_events = [
        _make_event(RunEvent.run_content.value, content="请问您的保障时段是？"),
        _make_event(RunEvent.run_completed.value, metrics=_make_metrics()),
    ]
    mock_agno_agent.arun = AsyncMock(return_value=_fake_stream(fake_events))
    chunks = await _collect_stream(mock_agno_agent, "我是直播用户")
    assert len(chunks) == 2
    assert chunks[0].content == "请问您的保障时段是？"


@pytest.mark.asyncio
async def test_stream_skill_tool_call_sequence(mock_agno_agent) -> None:
    """Skills 元工具调用事件序列应完整传递"""
    fake_events = [
        _make_event(RunEvent.tool_call_started.value,
                    tool=_make_tool_exec("get_skill_instructions", {"skill_name": "intent_parser"})),
        _make_event(RunEvent.tool_call_completed.value,
                    tool=_make_tool_exec("get_skill_instructions", {}, result="[instructions text]")),
        _make_event(RunEvent.tool_call_started.value,
                    tool=_make_tool_exec("get_skill_script",
                                         {"skill_name": "intent_parser",
                                          "script_path": "extract.py",
                                          "execute": True,
                                          "args": ["{}"]},
                                         )),
        _make_event(RunEvent.tool_call_completed.value,
                    tool=_make_tool_exec("get_skill_script", {},
                                         result='{"stdout": "{\\"complete\\":false}", "returncode": 0}')),
        _make_event(RunEvent.run_content.value, content="请告诉我您的用户类型"),
        _make_event(RunEvent.run_completed.value, metrics=_make_metrics()),
    ]
    mock_agno_agent.arun = AsyncMock(return_value=_fake_stream(fake_events))
    chunks = await _collect_stream(mock_agno_agent, "帮我优化网络")
    event_types = [c.event for c in chunks]
    assert event_types.count(RunEvent.tool_call_started.value) == 2
    assert event_types.count(RunEvent.tool_call_completed.value) == 2
    assert RunEvent.run_content.value in event_types


@pytest.mark.asyncio
async def test_stream_reasoning_events(mock_agno_agent) -> None:
    """推理模型的 reasoning_content_delta 事件应被完整传递"""
    fake_events = [
        _make_event(RunEvent.reasoning_content_delta.value, reasoning_content="分析用户意图..."),
        _make_event(RunEvent.run_content.value, content="好的，请补充保障时段"),
        _make_event(RunEvent.run_completed.value, metrics=_make_metrics()),
    ]
    mock_agno_agent.arun = AsyncMock(return_value=_fake_stream(fake_events))
    chunks = await _collect_stream(mock_agno_agent, "我是直播用户")
    event_types = [c.event for c in chunks]
    assert RunEvent.reasoning_content_delta.value in event_types


@pytest.mark.asyncio
async def test_stream_propagates_exception(mock_agno_agent) -> None:
    """Agent 异常应向上传播，不被吞掉"""
    async def failing_stream():
        raise RuntimeError("LLM 连接超时")
        yield

    mock_agno_agent.arun = AsyncMock(return_value=failing_stream())
    with pytest.raises(RuntimeError, match="LLM 连接超时"):
        await _collect_stream(mock_agno_agent, "test")
