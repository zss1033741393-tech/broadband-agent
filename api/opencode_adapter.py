"""OpenCode 事件 → 前端 SSE 协议转译器。

与 event_adapter.py 输出完全相同的 SSE 事件格式，
但数据源是 OpenCode Server 的 /event SSE 流而非 agno Team.arun 事件流。
"""

from __future__ import annotations

import time
import uuid
from typing import Any, AsyncGenerator, Optional

from loguru import logger

from api.event_adapter import (
    _MEMBER_DISPLAY_NAMES,
    MessageAggregate,
    StepAggregate,
    _emit_experience_assurance_result,
    _emit_insight_render,
    _emit_phase_render_blocks,
    _emit_wifi_simulation_render,
    _parse_stdout,
)
from api.sse import format_sse

_log = logger.bind(channel="opencode_adapter")


def _extract_skill_name(tool_input: dict[str, Any]) -> str:
    """从 tool input 中提取 skill_name。"""
    return tool_input.get("skill_name", "")


async def adapt_opencode(
    conv_id: str,
    event_stream: AsyncGenerator[dict[str, Any], None],
) -> AsyncGenerator[tuple[str, MessageAggregate], None]:
    """消费 OpenCode 事件流，yield (SSE字符串, MessageAggregate) 元组。

    输出格式与 event_adapter.adapt() 完全一致，前端无感切换。

    关键设计决策：
    - orchestrator 不建 StepAggregate（与 agno leader 对齐，内容落顶层）
    - session.idle 是唯一终止信号（message.updated(completed) 在多 agent 场景下多次触发）
    - tinput 优先用 running 事件缓存，fallback 到 completed 事件的 state.input
    - get_skill_script 默认视为 execute=True（OpenCode 侧 SKILL.md 始终带 execute=True）
    """
    agg = MessageAggregate(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
    )

    steps_by_agent: dict[str, StepAggregate] = {}
    current_agent: Optional[str] = None
    tool_start_times: dict[str, float] = {}
    tool_inputs: dict[str, dict[str, Any]] = {}
    thinking_start: Optional[float] = None
    thinking_end: Optional[float] = None

    try:
        async for event in event_stream:
            etype = event.get("type", "")
            props = event.get("properties", {})

            # ── message.part.updated — Part 级增量更新 ──
            if etype == "message.part.updated":
                part = props.get("part", {})
                delta = props.get("delta")
                ptype = part.get("type", "")
                msg_role = props.get("info", {}).get("role", "assistant")

                # ── reasoning → thinking ──
                if ptype == "reasoning":
                    if thinking_start is None:
                        thinking_start = time.monotonic()
                    content = delta or part.get("text", "")
                    if content:
                        agg.thinking_content += content
                        # orchestrator thinking → 空 stepId（与 agno leader 对齐，落顶层）
                        step_id = (
                            current_agent
                            if (current_agent and current_agent in steps_by_agent)
                            else ""
                        )
                        yield (
                            format_sse(
                                "thinking",
                                {
                                    "delta": content,
                                    "stepId": step_id,
                                },
                            ),
                            agg,
                        )

                # ── text → text（跳过用户消息 echo）──
                elif ptype == "text":
                    if msg_role == "user":
                        # OpenCode 在用户发消息时会触发一条 user-role 的 text part，
                        # 过滤掉，否则前端会把用户输入当 assistant 回复复读一遍。
                        continue
                    content = delta or part.get("text", "")
                    if content:
                        agg.content += content
                        if current_agent and current_agent in steps_by_agent:
                            steps_by_agent[current_agent].text_content += content
                        # 向 member step 的文本区路由：若当前是已知 subagent 则带 stepId
                        step_id = (
                            current_agent
                            if (current_agent and current_agent in steps_by_agent)
                            else None
                        )
                        payload: dict[str, Any] = {"delta": content}
                        if step_id:
                            payload["stepId"] = step_id
                        yield format_sse("text", payload), agg

                # ── agent part：只为 _MEMBER_DISPLAY_NAMES 里的 subagent 建 step ──
                # orchestrator 不建 step（与 agno leader 对齐，内容直接落顶层）
                elif ptype == "agent":
                    agent_name = part.get("name", "")
                    if not agent_name:
                        continue
                    if thinking_start and not thinking_end:
                        thinking_end = time.monotonic()
                    current_agent = agent_name
                    if agent_name in _MEMBER_DISPLAY_NAMES and agent_name not in steps_by_agent:
                        step = StepAggregate(
                            step_id=agent_name,
                            title=_MEMBER_DISPLAY_NAMES[agent_name],
                        )
                        steps_by_agent[agent_name] = step
                        agg.steps.append(step)
                        yield (
                            format_sse(
                                "step_start",
                                {
                                    "stepId": agent_name,
                                    "title": step.title,
                                },
                            ),
                            agg,
                        )

                # ── subtask → step_start（Task tool 委派给 subagent）──
                elif ptype == "subtask":
                    # OpenCode subtask part 的 agent 字段可能有多种写法
                    agent_name = (
                        part.get("agent")
                        or part.get("agentID")
                        or part.get("name")
                        or ""
                    )
                    _log.debug(f"subtask part fields={list(part.keys())} agent_name={agent_name!r}")
                    if agent_name and agent_name not in steps_by_agent:
                        current_agent = agent_name
                        title = _MEMBER_DISPLAY_NAMES.get(agent_name, agent_name)
                        step = StepAggregate(step_id=agent_name, title=title)
                        steps_by_agent[agent_name] = step
                        agg.steps.append(step)
                        yield (
                            format_sse(
                                "step_start",
                                {
                                    "stepId": agent_name,
                                    "title": title,
                                },
                            ),
                            agg,
                        )

                # ── tool → sub_step 生命周期 ──
                elif ptype == "tool":
                    call_id = part.get("callID", "")
                    tool_name = part.get("tool", "")
                    state = part.get("state", {})
                    status = state.get("status", "")

                    _log.debug(
                        f"tool part tool={tool_name!r} callID={call_id!r} status={status!r}"
                    )

                    if status == "running":
                        tool_start_times[call_id] = time.monotonic()
                        tool_inputs[call_id] = state.get("input", {})

                    elif status == "completed":
                        t0 = tool_start_times.pop(call_id, None)
                        duration_ms = int((time.monotonic() - t0) * 1000) if t0 else 0
                        # 优先用 running 事件缓存的 input；
                        # fallback 到 completed 事件里的 state.input（running 未到时的兜底）
                        tinput = tool_inputs.pop(call_id, state.get("input", {}))
                        skill_name = _extract_skill_name(tinput)
                        stdout = state.get("output", "")
                        step_id = current_agent or ""

                        # OpenCode 下 get_skill_script 始终是执行调用（SKILL.md 恒带 execute=True）；
                        # execute 字段缺失时默认 True，避免 tinput 为空时误判为 False。
                        is_exec = tool_name == "get_skill_script" and tinput.get(
                            "execute", True
                        )
                        is_load = tool_name in (
                            "get_skill_instructions",
                            "get_skill_reference",
                        )

                        if is_exec or is_load:
                            sub_step_id = f"{step_id}_{call_id}"
                            sub: dict[str, Any] = {
                                "subStepId": sub_step_id,
                                "name": skill_name or tool_name,
                                "completedAt": "",
                                "durationMs": duration_ms,
                                "scriptPath": tinput.get("script_path", ""),
                                "callArgs": tinput.get("args", []),
                                "stdout": stdout[:2000] if is_exec else "",
                                "stderr": "",
                            }

                            if current_agent and current_agent in steps_by_agent:
                                steps_by_agent[current_agent].sub_steps.append(sub)
                                steps_by_agent[current_agent].items.append(
                                    {"type": "sub_step", "data": sub}
                                )

                            yield format_sse("sub_step", {"stepId": step_id, **sub}), agg

                        # ── 业务渲染块解析（复用 agno adapter 的函数）──
                        if is_exec and stdout:
                            for sse_chunk, updated_agg in _emit_renders(
                                skill_name,
                                stdout,
                                sub_step_id if (is_exec or is_load) else f"{step_id}_{call_id}",
                                step_id,
                                agg,
                            ):
                                yield sse_chunk, updated_agg

                    elif status == "error":
                        error_msg = state.get("error", "工具执行失败")
                        _log.error(f"tool error: {tool_name} call_id={call_id} error={error_msg}")

                # ── step-finish → step_end ──
                elif ptype == "step-finish":
                    if current_agent and current_agent in steps_by_agent:
                        yield (
                            format_sse(
                                "step_end",
                                {
                                    "stepId": current_agent,
                                },
                            ),
                            agg,
                        )

                    tokens = part.get("tokens", {})
                    agg.input_tokens += tokens.get("input", 0)
                    agg.output_tokens += tokens.get("output", 0)
                    agg.reasoning_tokens += tokens.get("reasoning", 0)
                    agg.total_tokens = agg.input_tokens + agg.output_tokens

            # ── message.updated — 消息级状态更新（只累计 token，不终止流）──
            # 注意：multi-agent 场景下，每个 SubAgent 完成后都会触发 message.updated(completed)，
            # 不能在此终止——必须等 session.idle 才能确认整个 session 已完成。
            elif etype == "message.updated":
                info = props.get("info", {})
                if info.get("role") == "assistant":
                    tokens = info.get("tokens", {})
                    # 累加（不覆盖），各 SubAgent 的 token 合计到同一个 agg
                    agg.input_tokens += tokens.get("input", 0)
                    agg.output_tokens += tokens.get("output", 0)
                    agg.reasoning_tokens += tokens.get("reasoning", 0)
                    agg.total_tokens = agg.input_tokens + agg.output_tokens

                    if info.get("time", {}).get("completed") and thinking_start:
                        thinking_end = thinking_end or time.monotonic()
                        agg.thinking_duration_sec = int(thinking_end - thinking_start)

            # ── session.error ──
            elif etype == "session.error":
                err_data = props.get("error", {})
                msg = err_data.get("data", {}).get("message", str(err_data))
                agg.status = "error"
                agg.error_message = msg
                yield format_sse("error", {"message": msg}), agg
                return

            # ── session.idle — 该 session 完成（唯一的终止信号）──
            elif etype == "session.idle":
                if agg.status == "streaming":
                    if thinking_start:
                        thinking_end = thinking_end or time.monotonic()
                        agg.thinking_duration_sec = int(thinking_end - thinking_start)
                    agg.status = "done"
                    yield (
                        format_sse(
                            "done",
                            {
                                "messageId": agg.message_id,
                                "thinkingDurationSec": agg.thinking_duration_sec,
                                "inputTokens": agg.input_tokens,
                                "outputTokens": agg.output_tokens,
                                "totalTokens": agg.total_tokens,
                                "reasoningTokens": agg.reasoning_tokens,
                            },
                        ),
                        agg,
                    )
                return

    except Exception as exc:
        _log.exception("opencode_adapter 异常")
        agg.status = "error"
        agg.error_message = str(exc)
        yield format_sse("error", {"message": f"OpenCode 执行失败：{exc}"}), agg


def _emit_renders(
    skill_name: str,
    stdout: str,
    sub_step_id: str,
    step_id: str,
    agg: MessageAggregate,
) -> list[tuple[str, MessageAggregate]]:
    """复用 agno event_adapter 的业务渲染解析函数。

    从 get_skill_script 的 stdout 中提取 insight 图表、wifi 热力图等，
    产出 render / report / wifi_result / experience_assurance_result 事件。
    """
    results: list[tuple[str, MessageAggregate]] = []

    # wifi_simulation 通道
    if skill_name == "wifi_simulation":
        for rb in _emit_wifi_simulation_render(agg.message_id, stdout):
            agg.render_blocks.append(rb)
            results.append((format_sse("wifi_result", rb), agg))

    # experience_assurance 通道
    elif skill_name == "experience_assurance":
        for rb in _emit_experience_assurance_result(stdout):
            agg.render_blocks.append(rb)
            results.append((format_sse("experience_assurance_result", rb), agg))

    # insight 通道
    elif step_id == "insight":
        parsed = _parse_stdout(stdout)
        if isinstance(parsed, dict) and "results" in parsed:
            render_list = _emit_phase_render_blocks(parsed)
        else:
            render_list = _emit_insight_render(skill_name, stdout, sub_step_id)
        for rb in render_list:
            agg.render_blocks.append(rb)
            results.append((format_sse("report", rb), agg))
            results.append((format_sse("render", rb), agg))

    return results
