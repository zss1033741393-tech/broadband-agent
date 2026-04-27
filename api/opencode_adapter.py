"""OpenCode 事件 → 前端 SSE 协议转译器。

与 event_adapter.py 输出完全相同的 SSE 事件格式，
但数据源是 OpenCode Server 的 /event SSE 流而非 agno Team.arun 事件流。

架构对齐说明（相对 agno event_adapter.py）：
  - step_start  ← task tool running + 首条子会话事件触发（唯一机制）
  - step_end    ← task tool completed 触发（唯一机制）
  - thinking    ← ptype==reasoning，按 routing_agent 路由 stepId
  - text        ← ptype==text，orchestrator(routing_agent=None) 落顶层，
                   sub-agent 落 step.text_content
  - sub_step    ← get_skill_script/get_skill_instructions/get_skill_reference completed
  - wifi_result / experience_assurance_result / report / render ← skill stdout 解析
  - done        ← session.idle（唯一终止信号）

关键修复（相对旧版）：
  Bug1: render 函数期望 {"stdout": "..."} 包装，而 OpenCode 输出原始 JSON 字符串；
        修复：_emit_renders 内部统一包装为 {"stdout": stdout} 再传给 agno render 函数。
  Bug2: ptype==agent / ptype==subtask handler 与 task_agent_map 机制并存导致重复
        step_start；修复：删除两个冗余 handler，只保留 task_agent_map 机制。
  Bug3: agg.content 误累积 sub-agent text；修复：只在 routing_agent is None 时写入。
  Bug4: StepAggregate.items 缺少 thinking/text 块，历史回放空白；修复：引入
        pending_thinking/pending_text，在 sub_step 前和 step_end 前 flush 到 items。
  Bug5: main_session_id 从首条事件推断存在竞态；修复：接受外部传入 session_id 直接初始化。
  Bug6: orchestrator token 被 step-finish 和 message.updated 双重累积；
        修复：message.updated 只保留 thinking_end 推断，token 统一由 step-finish 计入。
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


def _flush_pending(step: StepAggregate) -> None:
    """把 pending_thinking / pending_text 按序 flush 进 step.items 并清零。

    调用时机：
      1. sub_step 事件到达之前（保证 thinking→text→sub_step 顺序）
      2. step_end 发出之前（收尾 sub-agent 最后一段文字/思考）
    """
    if step.pending_text:
        step.items.append({"type": "text", "content": step.pending_text})
        step.pending_text = ""
    if step.pending_thinking:
        step.items.append({
            "type": "thinking",
            "content": step.pending_thinking,
            "startedAt": 0,
            "endedAt": 0,
        })
        step.pending_thinking = ""


async def adapt_opencode(
    conv_id: str,
    event_stream: AsyncGenerator[dict[str, Any], None],
    session_id: Optional[str] = None,
) -> AsyncGenerator[tuple[str, MessageAggregate], None]:
    """消费 OpenCode 事件流，yield (SSE字符串, MessageAggregate) 元组。

    输出格式与 event_adapter.adapt() 完全一致，前端无感切换。

    Args:
        conv_id:      业务会话 ID
        event_stream: opencode_bridge.send_and_stream() 产出的原始事件流
        session_id:   OpenCode 主会话 ID（由 bridge.ensure_session 获取）；
                      直接初始化 main_session_id，消除首条事件竞态风险。
    """
    agg = MessageAggregate(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
    )

    steps_by_agent: dict[str, StepAggregate] = {}
    current_agent: Optional[str] = None

    # Bug5 fix: 外部传入 session_id 直接初始化，无需从首条事件推断
    main_session_id: Optional[str] = session_id

    tool_start_times: dict[str, float] = {}
    tool_inputs: dict[str, dict[str, Any]] = {}
    # task tool call_id → subagent_type；task.running 注册，task.completed 弹出
    task_agent_map: dict[str, str] = {}
    thinking_start: Optional[float] = None
    thinking_end: Optional[float] = None
    # 跟踪 user 消息 ID（从 message.updated(role=user) 提取）
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

                # ── session-aware routing ──────────────────────────────────────
                # part.sessionID 区分来源：
                #   orchestrator 事件 → part.sessionID == main_session_id → 顶层渲染
                #   sub-agent 事件   → part.sessionID != main_session_id → sub-agent step 渲染
                #
                # step_start 触发逻辑（唯一机制）：
                #   task tool running → 注册 task_agent_map[call_id] = subagent_type
                #   首条子会话事件到达（part_session != main_session_id）→ 建 step + emit step_start
                #   （不再依赖 ptype==agent / ptype==subtask，两者已删除）
                if main_session_id is None and part_session:
                    # session_id 未外部传入时，从首条 orchestrator 事件推断（回退路径）
                    main_session_id = part_session

                if part_session and main_session_id:
                    if part_session == main_session_id:
                        # Orchestrator 事件：顶层渲染
                        routing_agent: Optional[str] = None
                    else:
                        # Sub-agent 事件：找当前活跃的 task agent
                        routing_agent = (
                            next(iter(task_agent_map.values()), None)
                            if task_agent_map
                            else None
                        )
                        # Bug2 fix: 只在首条子会话事件时建 step（task_agent_map 机制，唯一）
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
                    routing_agent = current_agent

                # ── reasoning → thinking ──────────────────────────────────────
                if ptype == "reasoning":
                    if thinking_start is None:
                        thinking_start = time.monotonic()
                    content = delta or part.get("text", "")
                    if content:
                        agg.thinking_content += content
                        # Bug4 fix: sub-agent thinking 写入 pending_thinking 供后续 flush 到 items
                        if routing_agent and routing_agent in steps_by_agent:
                            steps_by_agent[routing_agent].pending_thinking += content
                        step_id_tk = (
                            routing_agent
                            if (routing_agent and routing_agent in steps_by_agent)
                            else ""
                        )
                        yield (
                            format_sse(
                                "thinking",
                                {
                                    "delta": content,
                                    "stepId": step_id_tk,
                                },
                            ),
                            agg,
                        )

                # ── text ─────────────────────────────────────────────────────
                elif ptype == "text":
                    # 用 part.messageID 过滤用户消息 echo
                    if part.get("messageID") in user_message_ids:
                        _log.debug(
                            f"skip user echo msgID={part.get('messageID')!r}"
                        )
                        continue
                    content = delta or part.get("text", "")
                    if content:
                        # Bug3 fix: 只有 orchestrator（routing_agent=None）的文本累积到 agg.content
                        if routing_agent is None:
                            agg.content += content
                        else:
                            # Bug4 fix: sub-agent text 写入 step.text_content 和 pending_text
                            if routing_agent in steps_by_agent:
                                steps_by_agent[routing_agent].text_content += content
                                steps_by_agent[routing_agent].pending_text += content

                        step_id_tx = (
                            routing_agent
                            if (routing_agent and routing_agent in steps_by_agent)
                            else None
                        )
                        payload: dict[str, Any] = {"delta": content}
                        if step_id_tx:
                            payload["stepId"] = step_id_tx
                        yield format_sse("text", payload), agg

                # ── tool → sub_step 生命周期 ──────────────────────────────────
                # Bug2 fix: 删除 ptype==agent 和 ptype==subtask handler，
                # step 生命周期完全由 task tool running/completed 驱动。
                elif ptype == "tool":
                    call_id = part.get("callID", "")
                    tool_name = part.get("tool", "")
                    state = part.get("state", {})
                    status = state.get("status", "")

                    _log.debug(
                        f"tool part tool={tool_name!r} callID={call_id!r} status={status!r}"
                    )

                    # ── task tool → sub-agent step 生命周期 ──────────────────
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
                                # Bug4 fix: step_end 前 flush pending
                                _flush_pending(steps_by_agent[task_agent])
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
                        tinput = tool_inputs.pop(call_id, state.get("input", {}))
                        skill_name = _extract_skill_name(tinput)
                        # OpenCode 工具输出即脚本原始 stdout（字符串）
                        stdout_raw = state.get("output", "")
                        step_id_tool = routing_agent or ""

                        is_exec = tool_name == "get_skill_script" and tinput.get(
                            "execute", True
                        )
                        is_load = tool_name in (
                            "get_skill_instructions",
                            "get_skill_reference",
                        )

                        if is_exec or is_load:
                            sub_step_id = f"{step_id_tool}_{call_id}"

                            # Bug4 fix: sub_step 到达前 flush pending_thinking/pending_text
                            if routing_agent and routing_agent in steps_by_agent:
                                _flush_pending(steps_by_agent[routing_agent])

                            sub: dict[str, Any] = {
                                "subStepId": sub_step_id,
                                "name": skill_name or tool_name,
                                "completedAt": "",
                                "durationMs": duration_ms,
                                "scriptPath": tinput.get("script_path", ""),
                                "callArgs": tinput.get("args", []),
                                "stdout": stdout_raw[:2000] if is_exec else "",
                                "stderr": "",
                            }

                            if routing_agent and routing_agent in steps_by_agent:
                                steps_by_agent[routing_agent].sub_steps.append(sub)
                                steps_by_agent[routing_agent].items.append(
                                    {"type": "sub_step", "data": sub}
                                )

                            yield format_sse("sub_step", {"stepId": step_id_tool, **sub}), agg

                        # ── 业务渲染块解析（Bug1 fix: 在 _emit_renders 内部包装格式）──
                        if is_exec and stdout_raw:
                            for sse_chunk, updated_agg in _emit_renders(
                                skill_name,
                                stdout_raw,
                                sub_step_id,
                                step_id_tool,
                                agg,
                            ):
                                yield sse_chunk, updated_agg

                    elif status == "error":
                        error_msg = state.get("error", "工具执行失败")
                        _log.error(f"tool error: {tool_name} call_id={call_id} error={error_msg}")

                # ── step-finish → token 累积（唯一 token 来源，覆盖 orchestrator + sub-agent）
                # Bug6 fix: token 统一从 step-finish 计入；message.updated 只做 thinking_end 推断。
                elif ptype == "step-finish":
                    tokens = part.get("tokens", {})
                    agg.input_tokens += tokens.get("input", 0)
                    agg.output_tokens += tokens.get("output", 0)
                    agg.reasoning_tokens += tokens.get("reasoning", 0)
                    agg.total_tokens = agg.input_tokens + agg.output_tokens
                    if thinking_start and not thinking_end:
                        thinking_end = time.monotonic()

            # ── message.updated — 用户消息追踪 + thinking_end 推断 ──────────────
            # Bug6 fix: 不再在此累积 token（避免与 step-finish 双重计数）。
            elif etype == "message.updated":
                info = props.get("info", {})
                msg_role = info.get("role", "")
                msg_id = info.get("id", "")

                if msg_role == "user" and msg_id:
                    user_message_ids.add(msg_id)
                    _log.info(f"tracked user message id={msg_id!r}")

                elif msg_role == "assistant":
                    # 仅用于 thinking_end 推断，不做 token 累积
                    if info.get("time", {}).get("completed") and thinking_start:
                        thinking_end = thinking_end or time.monotonic()
                        agg.thinking_duration_sec = int(thinking_end - thinking_start)

            # ── session.error ─────────────────────────────────────────────────
            elif etype == "session.error":
                err_data = props.get("error", {})
                msg = err_data.get("data", {}).get("message", str(err_data))
                agg.status = "error"
                agg.error_message = msg
                yield format_sse("error", {"message": msg}), agg
                return

            # ── session.idle — 唯一终止信号 ───────────────────────────────────
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
    stdout_raw: str,
    sub_step_id: str,
    step_id: str,
    agg: MessageAggregate,
) -> list[tuple[str, MessageAggregate]]:
    """解析 get_skill_script 的原始 stdout，产出 render/wifi_result/report 等事件。

    Bug1 fix:
      OpenCode 工具输出 stdout_raw 是脚本的原始字符串（如 wifi_simulation 产出的 JSON）。
      agno 的 render 辅助函数（_emit_wifi_simulation_render 等）内部调用 _parse_stdout()，
      而 _parse_stdout() 期望的格式是 agno 包装 {"stdout": "<json>", "stderr": ""}。
      修复方案：统一在此处包装为 {"stdout": stdout_raw} 再传给这些函数。
    """
    results: list[tuple[str, MessageAggregate]] = []

    # 包装为 agno render 函数期望的格式（Bug1 核心修复）
    wrapped = {"stdout": stdout_raw}

    # wifi_simulation 通道
    if skill_name == "wifi_simulation":
        for rb in _emit_wifi_simulation_render(agg.message_id, wrapped):
            agg.render_blocks.append(rb)
            results.append((format_sse("wifi_result", rb), agg))

    # experience_assurance 通道
    elif skill_name == "experience_assurance":
        for rb in _emit_experience_assurance_result(wrapped):
            agg.render_blocks.append(rb)
            results.append((format_sse("experience_assurance_result", rb), agg))

    # insight 通道
    elif step_id == "insight":
        parsed = _parse_stdout(wrapped)
        if isinstance(parsed, dict) and "results" in parsed:
            render_list = _emit_phase_render_blocks(parsed)
        else:
            render_list = _emit_insight_render(skill_name, wrapped, sub_step_id)
        for rb in render_list:
            agg.render_blocks.append(rb)
            results.append((format_sse("report", rb), agg))
            results.append((format_sse("render", rb), agg))

    return results
