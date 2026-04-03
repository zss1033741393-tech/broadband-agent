"""Agno Agent 定义

架构说明：
  - 使用 agno.agent.Agent + OpenAILike 模型，不直接操作 OpenAI client
  - Skills 通过 skill_loader.build_agno_tools() 注册为真实 Agno Function tools
    LLM 通过 tool_call 机制真实调用，不是文本提及
  - 输出通过 run_stream() 以 AgentChunk 流式产出（中间层）

中间层 AgentChunk 统一处理模型三类返回：
  reasoning_content  — 推理模型的思考增量（DeepSeek-R1 / QwQ 等）
  content            — 正文 content 增量
  tool_call          — Skill 调用开始 / 完成事件
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

from agno.agent import Agent
from agno.models.openai import OpenAILike
from agno.run.agent import (
    RunEvent,
    ReasoningContentDeltaEvent,
    RunContentEvent,
    ToolCallStartedEvent,
    ToolCallCompletedEvent,
    RunCompletedEvent,
)

from app.agent.skill_loader import build_agno_tools, build_skills_summary, discover_skills
from app.agent.tracer import AgentTracer
from app.config import get_model_config

logger = logging.getLogger("agent")


# ─────────────────────────────────────────────────────────────
# 中间层：规范化的流式输出块
# ─────────────────────────────────────────────────────────────

@dataclass
class AgentChunk:
    """Agent 流式输出的最小单元。

    type 取值说明：
      reasoning_delta   — reasoning_content 增量（推理模型专有）
      content_delta     — 正文 content 增量，流式追加到对话气泡
      tool_call_started — Skill 被 LLM 触发调用，tool_name/tool_args 有值
      tool_call_done    — Skill 执行完成，tool_result 有值
      done              — 本轮对话结束，metrics 包含 token 和耗时统计
    """

    type: Literal["reasoning_delta", "content_delta", "tool_call_started", "tool_call_done", "done"]
    delta: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# 中间层：RunOutputEvent → AgentChunk 解析器
# ─────────────────────────────────────────────────────────────

class StreamEventParser:
    """将 Agno RunOutputEvent 流规范化为 AgentChunk。

    Agno stream_events=True 时，不同模型返回的事件组合不同：
      普通模型     : RunContentEvent(content)
      推理模型     : ReasoningContentDeltaEvent → RunContentEvent
      工具调用     : ToolCallStartedEvent → ToolCallCompletedEvent → RunContentEvent
      本轮结束     : RunCompletedEvent（含 metrics）

    本层屏蔽这些差异，上层只需按 AgentChunk.type 分支处理。
    """

    def parse(self, event: Any) -> AgentChunk | None:
        event_type = getattr(event, "event", None)

        if event_type == RunEvent.reasoning_content_delta.value:
            # 推理模型思考内容增量
            rc: str = getattr(event, "reasoning_content", "") or ""
            if rc:
                return AgentChunk(type="reasoning_delta", delta=rc)

        elif event_type == RunEvent.run_content.value:
            # 正文增量；content 可能是 str / None
            content = getattr(event, "content", None)
            if content:
                return AgentChunk(type="content_delta", delta=str(content))

        elif event_type == RunEvent.tool_call_started.value:
            tool_exec = getattr(event, "tool", None)
            if tool_exec:
                return AgentChunk(
                    type="tool_call_started",
                    tool_name=tool_exec.tool_name or "",
                    tool_args=tool_exec.tool_args or {},
                )

        elif event_type == RunEvent.tool_call_completed.value:
            tool_exec = getattr(event, "tool", None)
            if tool_exec:
                return AgentChunk(
                    type="tool_call_done",
                    tool_name=tool_exec.tool_name or "",
                    tool_result=tool_exec.result or "",
                )

        elif event_type == RunEvent.run_completed.value:
            return AgentChunk(type="done", metrics=_extract_metrics(event))

        return None


def _extract_metrics(event: RunCompletedEvent) -> dict[str, Any]:
    m = getattr(event, "metrics", None)
    if not m:
        return {}
    return {
        "input_tokens": getattr(m, "input_tokens", 0),
        "output_tokens": getattr(m, "output_tokens", 0),
        "total_tokens": getattr(m, "total_tokens", 0),
        "time": round(getattr(m, "time", 0) or 0, 3),
    }


# ─────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = """\
# 你是家宽体验感知优化 Agent

你是一个智能配置生成助手。用户描述保障需求，你需要理解意图、生成优化方案、校验约束、输出设备配置。

## 工作指导（建议顺序，可根据实际灵活调整）

1. 先理解用户意图，信息不完整时追问
2. 收集到足够信息后，填充对应的方案模板
3. 填充完成后进行约束校验
4. 校验通过后转译为设备配置

调整场景：
- 用户给出完整参数 → 跳过追问直接填充
- 某方案无需修改 → 保持默认值
- 校验发现冲突 → 回退调整方案参数
- 用户中途改需求 → 重新理解意图

## 可用 Skills（已注册为工具，直接调用即可）

{skills_summary}
"""


# ─────────────────────────────────────────────────────────────
# Agent 主体
# ─────────────────────────────────────────────────────────────

class BroadbandAgent:
    """家宽体验感知优化 Agent。

    内部使用 Agno Agent + OpenAILike 模型。
    每个 Skill 注册为真实的 Agno Function tool，由 LLM 通过 tool_call 调用，
    不再依赖文本解析来"推断" Skill 使用情况。

    对外只暴露 run_stream()，调用方通过 async for 迭代 AgentChunk。
    """

    def __init__(self) -> None:
        self._parser = StreamEventParser()

        skills = discover_skills()
        agno_tools = build_agno_tools(skills)
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            skills_summary=build_skills_summary(skills)
        )

        model_cfg = get_model_config("main")
        model = OpenAILike(
            id=model_cfg.get("model", "gpt-4o"),
            api_key=model_cfg.get("api_key", "sk-xxx"),
            base_url=model_cfg.get("base_url", "https://api.openai.com/v1"),
            temperature=model_cfg.get("temperature", 0.7),
            max_tokens=model_cfg.get("max_tokens", 4096),
        )

        self._agent = Agent(
            model=model,
            tools=agno_tools,
            system_prompt=system_prompt,
            # Agno 原生维护对话历史，不需要外部手动拼接 messages
            add_history_to_messages=True,
            num_history_responses=10,
            stream=True,
        )

        logger.info(
            "BroadbandAgent 初始化完成 | model=%s | skills=%d | agno_tools=%d",
            model_cfg.get("model"),
            len(skills),
            len(agno_tools),
        )

    async def run_stream(
        self,
        user_message: str,
        session_id: str,
        tracer: AgentTracer,
    ) -> AsyncIterator[AgentChunk]:
        """流式运行 Agent，yield AgentChunk 中间层事件。

        调用方按 chunk.type 处理：
          reasoning_delta   → 累积到思考面板（折叠展示）
          content_delta     → 流式追加到对话气泡
          tool_call_started → 显示 Skill 调用进度
          tool_call_done    → 显示 Skill 返回结果摘要
          done              → 记录 metrics，关闭进度指示
        """
        tracer.log("user_input", content=user_message)
        logger.debug("[Agent] run_stream 开始 | session=%s", session_id)

        try:
            event_stream = await self._agent.arun(
                user_message,
                session_id=session_id,
                stream=True,
                stream_events=True,
            )

            async for event in event_stream:
                chunk = self._parser.parse(event)
                if chunk is None:
                    continue
                self._trace_chunk(chunk, tracer)
                yield chunk

        except Exception as exc:
            logger.error("[Agent] run_stream 异常 | error=%s", exc)
            tracer.log("run_error", error=str(exc))
            raise

    def _trace_chunk(self, chunk: AgentChunk, tracer: AgentTracer) -> None:
        """将 AgentChunk 映射到 tracer 事件（仅记录关键节点，不记录每个增量）"""
        if chunk.type == "tool_call_started":
            tracer.log("skill_load", skill=chunk.tool_name, args=chunk.tool_args)
            logger.info(
                "[Skill:%s] Agent 调用 Skill | args=%s",
                chunk.tool_name,
                chunk.tool_args,
            )
        elif chunk.type == "tool_call_done":
            tracer.log(
                "skill_execute",
                skill=chunk.tool_name,
                result_preview=chunk.tool_result[:200],
            )
            logger.info(
                "[Skill:%s] 执行完成 | result_len=%d",
                chunk.tool_name,
                len(chunk.tool_result),
            )
        elif chunk.type == "done":
            tracer.log("run_completed", metrics=chunk.metrics)
            logger.info(
                "[Agent] 本轮完成 | tokens=%s | time=%.3fs",
                chunk.metrics.get("total_tokens"),
                chunk.metrics.get("time", 0),
            )
