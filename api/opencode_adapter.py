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
    # 主会话 ID：从第一条 message.part.updated 的 part.sessionID 推断，
    # 用于区分 orchestrator 事件（同主会话）和 sub-agent 事件（子会话）。
    main_session_id: Optional[str] = None
    tool_start_times: dict[str, float] = {}
    tool_inputs: dict[str, dict[str, Any]] = {}
    # task tool call_id → subagent_type；task.running 时注册、task.completed 时弹出
    task_agent_map: dict[str, str] = {}
    thinking_start: Optional[float] = None
    thinking_end: Optional[float] = None
    # 跟踪 user 消息 ID（从 message.updated(role=user) 提取，含子会话）
    # 用于过滤 message.part.updated 中用户消息的 TextPart echo
    user_message_ids: set[str] = set()

    try:
        async for event in event_stream:
            etype = event.get("type", "")
            props = event.get("properties", {})

            # ── message.part.updated — Part 级增量更新 ──
            if etype == "message.part.updated":
                part = props.get("part", {})
                delta = props.get("delta")
                ptype = part.get("type", "")
                part_session = part.get("sessionID", "")

                # ── session-aware routing ─────────────────────────────────
                # part.sessionID 区分来源：
                #   orchestrator 事件 → part.sessionID == main_session_id → 顶层渲染
                #   sub-agent 事件   → part.sessionID != main_session_id → sub-agent step 渲染
                #
                # 不能依赖 task.running 设置 current_agent，因为 task.running 在
                # orchestrator reasoning 流式结束前就触发（并发）。
                # 改为：task.running 仅注册 task_agent_map；
                # sub-agent 首条事件到达（part_session != main_session_id）时延迟建 step。
                if main_session_id is None and part_session:
                    main_session_id = part_session

                if part_session and main_session_id:
                    if part_session == main_session_id:
                        # Orchestrator 事件：无论 current_agent 是什么，均顶层渲染
                        routing_agent: Optional[str] = None
                    else:
                        # Sub-agent 事件：找当前活跃的 task agent
                        routing_agent = (
                            next(iter(task_agent_map.values()), None)
                            if task_agent_map
                            else None
                        )
                        # 首条子会话事件到达时，建立 step 并 emit step_start
                        if (
                            routing_agent
                            and routing_agent in _MEMBER_DISPLAY_NAMES
                            and routing_agent not in steps_by_agent
                        ):
                            current_agent = routing_agent
                            _step = StepAggregate(
                                step_id=routing_agent,
                                title=_MEMBER_DISPLAY_NAMES[routing_agent],
                            )
                            steps_by_agent[routing_agent] = _step
                            agg.steps.append(_step)
                            yield (
                                format_sse(
                                    "step_start",
                                    {
                                        "stepId": routing_agent,
                                        "title": _step.title,
                                    },
                                ),
                                agg,
                            )
                        elif routing_agent in steps_by_agent if routing_agent else False:
                            current_agent = routing_agent
                else:
                    # 无会话信息（session.idle 等），回退到 current_agent
                    routing_agent = current_agent

                # ── reasoning → thinking ──
                if ptype == "reasoning":
                    if thinking_start is None:
                        thinking_start = time.monotonic()
                    content = delta or part.get("text", "")
                    if content:
                        agg.thinking_content += content
                        # 用 routing_agent 路由：orchestrator → ""（顶层），sub-agent → stepId
                        step_id = (
                            routing_agent
                            if (routing_agent and routing_agent in steps_by_agent)
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
                    # EventMessagePartUpdated.properties 只有 {part, delta}，
                    # 没有 info.role，所以不能通过 role 过滤。
                    # 正确做法：用 part.messageID 比对已知 user 消息 ID 集合。
                    if part.get("messageID") in user_message_ids:
                        _log.debug(
                            f"skip user echo msgID={part.get('messageID')!r}"
                        )
                        continue
                    content = delta or part.get("text", "")
                    if content:
                        agg.content += content
                        if routing_agent and routing_agent in steps_by_agent:
                            steps_by_agent[routing_agent].text_content += content
                        # 用 routing_agent 路由：sub-agent 带 stepId，orchestrator 不带
                        step_id = (
                            routing_agent
                            if (routing_agent and routing_agent in steps_by_agent)
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
                    _log.info(
                        f"subtask part keys={list(part.keys())} "
                        f"agent={agent_name!r} sid={part.get('sessionID')!r}"
                    )
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

                    # ── task tool → sub-agent step 生命周期 ──
                    # orchestrator 通过 task tool 把工作委派给 sub-agent。
                    # running 时只注册 task_agent_map（不提前建 step，因为 task.running
                    # 会在 orchestrator 的 reasoning 流结束前触发，提前设置会导致
                    # orchestrator 内容错误落入 sub-agent step）。
                    # step_start 由第一条子会话事件（part.sessionID != main_session_id）延迟触发。
                    # task.completed 时发 step_end 并清理状态。
                    if tool_name == "task":
                        if status == "running":
                            subagent_type = state.get("input", {}).get("subagent_type", "")
                            if subagent_type and subagent_type in _MEMBER_DISPLAY_NAMES:
                                task_agent_map[call_id] = subagent_type
                                _log.info(
                                    f"task tool running → registered stepId={subagent_type!r}"
                                )
                        elif status == "completed":
                            task_agent = task_agent_map.pop(call_id, None)
                            if task_agent and task_agent in steps_by_agent:
                                _log.info(
                                    f"task tool completed → step_end stepId={task_agent!r}"
                                )
                                yield (
                                    format_sse("step_end", {"stepId": task_agent}),
                                    agg,
                                )
                            if current_agent == task_agent:
                                current_agent = None
                        continue

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
                        # 用 routing_agent 路由：sub-agent 的工具调用落入其 step
                        step_id = routing_agent or ""

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

                            if routing_agent and routing_agent in steps_by_agent:
                                steps_by_agent[routing_agent].sub_steps.append(sub)
                                steps_by_agent[routing_agent].items.append(
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
                # task 运行期间（task_agent_map 非空）step_end 由 task.completed 触发；
                # sub-agent 的多个 step-finish 不重复发 step_end。
                elif ptype == "step-finish":
                    if not task_agent_map and routing_agent and routing_agent in steps_by_agent:
                        yield (
                            format_sse(
                                "step_end",
                                {
                                    "stepId": routing_agent,
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
                msg_role = info.get("role", "")
                msg_id = info.get("id", "")

                if msg_role == "user" and msg_id:
                    # 记录 user 消息 ID，供 TextPart echo 过滤使用
                    user_message_ids.add(msg_id)
                    _log.info(f"tracked user message id={msg_id!r}")

                elif msg_role == "assistant":
                    tokens = info.get("tokens", {})
                    # 各 assistant 消息（orchestrator + sub-agent）的 token 累加
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
