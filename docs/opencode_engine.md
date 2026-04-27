# Agno ↔ OpenCode 双引擎架构差异分析与对齐方案

> **版本**: v1.0 | **日期**: 2026-04-27
> **目标**: 梳理当前 OpenCode 引擎相对 Agno 引擎在事件流、前后端交互上的核心差异，定位"内容错乱"的根因，并给出对齐修复方案。

---

## 1. 问题现象回顾

### 1.1 WiFi 仿真场景（输入"wifi仿真"）

**Agno 引擎正常流程**：

```
用户输入 → Orchestrator thinking → step_start("provisioning-wifi")
→ SubAgent thinking → get_skill_script("wifi_simulation") → sub_step
→ wifi_result 渲染 → SubAgent text → step_end
→ Orchestrator text 总结 → done
```

**OpenCode 引擎实际表现**：SubAgent 内容先于 Orchestrator 思考出现；step_start 延迟或缺失；wifi_result 渲染事件和主 Agent 文本交错混乱；最终 done 信号可能缺失或过早触发。

### 1.2 网络覆盖分析场景（输入"请分析当前网络家庭wifi覆盖情况"）

**Agno 引擎正常流程**：

```
Orchestrator thinking → step_start("insight")
→ InsightAgent thinking → 多个 skill 调用 → sub_step × N
→ report/render 渲染 → InsightAgent text → step_end
→ Orchestrator text 总结 → done
```

**OpenCode 引擎实际表现**：SubAgent 内容先出现；主 Agent 内容全乱序；最终未生成对应报告（render/report 事件缺失或格式错误）。

---

## 2. 根因分析：两种引擎的架构本质差异

### 2.1 事件模型根本不同

Agno 和 OpenCode 的事件流在本质结构上有根本性差异，这是所有问题的源头。

#### Agno：层级化事件流（自带归属标识）

Agno 的 `Team.arun()` 产出的事件流是**带有层级标识的扁平流**：每个事件自带 `leader/member` 标志位和 `agent_id`/`agent_name` 属性，适配器可以直接判断事件归属。

```
事件对象属性:
  ├─ event_type: "ReasoningContentDelta" / "RunContent" / "ToolCallStarted" / ...
  ├─ agent_id:   UUID（member 事件）或空（leader 事件需看 team_id）
  ├─ agent_name: "insight" / "provisioning-wifi" / ...
  └─ 原始事件名带前缀区分: "TeamReasoningContentDelta" = leader, "ReasoningContentDelta" = member
```

关键特征：
- **step_start 触发明确**：leader 的 `ToolCallStarted(delegate_task_to_member)` 事件直接携带 `member_id`，100% 确定性触发。
- **事件归属无歧义**：每个事件通过 `agent_id` + `agent_name` 双重标识路由到正确的 StepAggregate。
- **终止信号明确**：leader 的 `RunCompleted` 事件标志整个流程结束。

#### OpenCode：扁平 Session-based 事件流（需推断归属）

OpenCode 的 `/event` SSE 端点产出的是**全局扁平事件流**，所有 session 的事件混在一起，按 Part 类型区分内容。事件归属需要通过 `part.sessionID` 与主 session ID 的比较来**推断**。

```
事件结构:
  ├─ type: "message.part.updated" / "message.updated" / "session.idle" / ...
  ├─ properties:
  │   ├─ part:
  │   │   ├─ type: "reasoning" / "text" / "tool" / "agent" / "subtask" / "step-finish"
  │   │   ├─ sessionID: 该 Part 所属消息的 session ID
  │   │   ├─ callID: (tool Part) 工具调用 ID
  │   │   └─ state: (tool Part) {status, input, output}
  │   ├─ delta: 增量文本
  │   └─ sessionID / info.sessionID: (会话级事件) 
  └─ 无 agent_name/agent_id 属性
```

关键特征：
- **step_start 触发是推断式的**：需要通过 task tool 的 running 状态注册 `task_agent_map`，再在首条子会话事件到达时才能建 step。
- **事件归属需推断**：通过 `part.sessionID == main_session_id?` 判断是 Orchestrator 还是 SubAgent。子会话的 sessionID 与主会话不同。
- **终止信号多源**：`session.idle`、`message.updated(completed)` 都可能表示完成，需要多重兜底。

### 2.2 差异对照表（核心维度）

| 维度 | Agno | OpenCode | 差异影响 |
|------|------|----------|----------|
| **事件归属标识** | `agent_id` + `agent_name` 直接携带 | `part.sessionID` 间接推断 | OpenCode 需要维护 session→agent 映射表 |
| **step_start 触发** | `ToolCallStarted(delegate_task_to_member)` → 确定性 | `task tool running` → 注册 + 首条子会话事件 → 延迟触发 | **根因1**：子会话事件可能先于 task tool running 到达 |
| **Leader/Member 区分** | 事件名前缀 "Team" vs 无前缀 | `part.sessionID == main_session_id` | **根因2**：main_session_id 推断竞态 |
| **事件顺序保证** | agno 内部 asyncio.Queue 保证因果序 | HTTP SSE 全局流，无因果序保证 | **根因3**：task.running 和 sub-session 首事件无序 |
| **工具调用完成** | `ToolCallCompleted` 自带 `agent_id` | `tool Part(completed)` 只有 `callID` | 需要 `tool_inputs` 字典反查 |
| **终止信号** | leader `RunCompleted`（唯一） | `session.idle` + `message.updated` 双重 | 需要状态机防止重复 done |
| **Token 统计** | `ModelRequestCompleted` 逐次上报 | `step-finish Part` + `message.updated` | Bug6：双重累积风险 |
| **Observability** | Tracer 写 sessions.db | OpenCode 内置 SQLite | OpenCode 通道无 Tracer 集成 |

---

## 3. 六大核心 Bug 详解

### Bug1：stdout 格式不匹配 → render 事件缺失

**现象**：WiFi 仿真、Insight 报告等业务渲染事件（`wifi_result`、`report`、`render`）不触发。

**根因**：
- Agno 的 `ToolCallCompleted` 事件 result 格式为 `{"stdout": "<json>", "stderr": ""}`（由 agno Skill 框架自动包装）
- OpenCode 的 tool Part output 是脚本的**原始 stdout 字符串**（无包装）
- `event_adapter.py` 的 `_parse_stdout()` 期望 `{"stdout": "..."}` 包装格式，直接传入原始字符串会解析失败

**修复状态**：`opencode_adapter.py` 的 `_emit_renders()` 已在内部包装 `{"stdout": stdout_raw}`，但需要验证所有 skill 路径（wifi_simulation / experience_assurance / insight_*）是否全覆盖。

### Bug2：step_start 重复触发

**现象**：同一个 SubAgent 的 step_start 被发送多次。

**根因**：
- 早期 `opencode_adapter.py` 同时实现了三套 step_start 触发机制：
  1. `ptype == "agent"` → step_start（AgentPart）
  2. `ptype == "subtask"` → step_start（Subtask Part）
  3. `task_agent_map` + 首条子会话事件 → step_start
- 三套机制并存，同一次委派触发多次 step_start

**修复状态**：已删除 handler 1 和 2，只保留 `task_agent_map` 机制。但该机制依赖 task tool running 事件先于子会话首条事件到达（见 Bug 与根因3 的关联）。

### Bug3：agg.content 误累积 SubAgent 文本

**现象**：Orchestrator 的最终文本混入 SubAgent 的回复内容，前端顶层正文区显示混乱。

**根因**：
- OpenCode 的 text Part 无法通过事件属性区分 leader/member
- 早期代码对所有 text 事件都累积到 `agg.content`
- Agno 侧只在 `RunContent + leader` 时累积

**修复状态**：已通过 `routing_agent is None` 条件守卫，只有 Orchestrator 文本写入 `agg.content`。SubAgent 文本写入 `step.text_content` 和 `step.pending_text`。

### Bug4：StepAggregate.items 缺内容 → 历史回放空白

**现象**：前端历史回放时，SubAgent 的步骤卡片内没有 thinking/text 内容。

**根因**：
- Agno 的 `event_adapter.py` 在 `ToolCallStarted` 时机 flush `pending_text`/`pending_thinking` 到 `step.items`
- OpenCode 适配器缺少等价的 flush 时机
- `step.items` 是前端历史回放的数据源，空则无内容

**修复状态**：引入 `_flush_pending()` 函数，在 sub_step 事件到达前和 step_end 发出前执行 flush。但需确认 flush 时机是否覆盖所有路径（特别是 SubAgent 只有 thinking 没有 tool call 的情况）。

### Bug5：main_session_id 推断竞态

**现象**：事件路由错误，Orchestrator 事件被当作 SubAgent 事件，或反之。

**根因**：
- 旧版从首条 `message.part.updated` 事件的 `part.sessionID` 推断 `main_session_id`
- 如果首条事件恰好是子会话事件（SubAgent 比 Orchestrator 先返回），则 `main_session_id` 被错误设为子会话 ID
- 后续所有路由逻辑全部反转

**修复状态**：`messages.py` 中提前调用 `oc.ensure_session()` 获取 session_id，直接传给 `adapt_opencode()`。但需确认 `ensure_session` 的缓存 `_session_map` 在 FastAPI 热重启时是否失效。

### Bug6：Token 双重累积

**现象**：Token 统计值异常偏高（实际的 2 倍）。

**根因**：
- OpenCode 事件流中，token 信息出现在两个位置：
  1. `step-finish Part` 的 `usage` 字段
  2. `message.updated(completed)` 的 `usage` 字段
- 如果两处都累加，则 Orchestrator 的 token 被重复计入

**修复状态**：`message.updated` 只保留 `thinking_end` 时间推断，token 统一由 `step-finish` 计入。但需确认 SubAgent 的 token 是否也存在类似问题。

---

## 4. 事件流对比：以"WiFi 仿真"为例

### 4.1 Agno 引擎事件流（理想时序）

```
┌─ agno Team.arun 事件流 ──────────────────────────────────────────────┐
│                                                                       │
│  1. TeamReasoningContentDelta (leader=True)                           │
│     → SSE: thinking { delta: "分析用户意图...", stepId: "" }           │
│                                                                       │
│  2. ToolCallStarted (leader=True, tool=delegate_task_to_member)       │
│     args: { member_id: "provisioning-wifi" }                          │
│     → SSE: step_start { stepId: "provisioning-wifi", title: "..." }   │
│                                                                       │
│  3. ReasoningContentDelta (leader=False, agent_name=provisioning-wifi)│
│     → SSE: thinking { delta: "需要调用 wifi_simulation...", stepId: "provisioning-wifi" } │
│                                                                       │
│  4. ToolCallStarted (leader=False, tool=get_skill_script)             │
│     args: { skill_name: "wifi_simulation", execute: True }            │
│     → (内部记录开始时间)                                                │
│                                                                       │
│  5. ToolCallCompleted (leader=False, tool=get_skill_script)           │
│     result: { stdout: "{...json...}", stderr: "" }                    │
│     → SSE: sub_step { stepId: "provisioning-wifi", name: "wifi_simulation", ... } │
│     → SSE: wifi_result { ... 解析 stdout 产出热力图数据 ... }           │
│                                                                       │
│  6. RunContent (leader=False, agent_name=provisioning-wifi)           │
│     → SSE: text { delta: "仿真完成，结果如下...", stepId: "provisioning-wifi" } │
│                                                                       │
│  7. ToolCallCompleted (leader=True, tool=delegate_task_to_member)     │
│     → SSE: step_end { stepId: "provisioning-wifi" }                   │
│                                                                       │
│  8. RunContent (leader=True)                                          │
│     → SSE: text { delta: "WiFi 仿真已完成..." }  ← 顶层总结           │
│                                                                       │
│  9. RunCompleted (leader=True)                                        │
│     → SSE: done { messageId, tokens... }                              │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

**关键特征**：事件 2（step_start）必然在事件 3（SubAgent thinking）之前，因为 agno 内部 leader 的 ToolCallStarted 是同步触发的。

### 4.2 OpenCode 引擎事件流（实际可能时序）

```
┌─ OpenCode /event SSE 流 ─────────────────────────────────────────────┐
│                                                                       │
│  1. message.part.updated { part.type=reasoning, part.sessionID=MAIN } │
│     → SSE: thinking { delta: "分析用户意图...", stepId: "" }  ✅        │
│                                                                       │
│  2. message.part.updated { part.type=tool, tool=task, status=running }│
│     state.input: { subagent_type: "provisioning-wifi" }               │
│     → 内部注册: task_agent_map[callID] = "provisioning-wifi"           │
│     → (此时 step 尚未创建，等首条子会话事件)                             │
│                                                                       │
│  ★ 竞态窗口：事件 2 和事件 3 之间无因果序保证                            │
│  ★ 如果事件 3 先于事件 2 到达 → step_start 无法触发                     │
│  ★ routing_agent 为 None → SubAgent 内容被当作 Orchestrator 内容        │
│                                                                       │
│  3. message.part.updated { part.type=reasoning, part.sessionID=SUB1 } │
│     → 检测到 SUB1 != MAIN → 查 task_agent_map → 找到 routing_agent     │
│     → 首次见到该 agent → step_start + thinking                         │
│     → SSE: step_start { stepId: "provisioning-wifi" }                 │
│     → SSE: thinking { delta: "...", stepId: "provisioning-wifi" }     │
│                                                                       │
│  4. message.part.updated { part.type=tool, tool=get_skill_script, status=running } │
│     → 内部记录开始时间                                                  │
│                                                                       │
│  5. message.part.updated { part.type=tool, tool=get_skill_script, status=completed }│
│     state.output: "{...json...}"  ← 原始 stdout，无 {"stdout": "..."} 包装 │
│     → SSE: sub_step { ... }                                            │
│     → _emit_renders() 包装为 {"stdout": raw} 后解析                     │
│     → SSE: wifi_result { ... }                                         │
│                                                                       │
│  6. message.part.updated { part.type=text, part.sessionID=SUB1 }      │
│     → routing_agent="provisioning-wifi" → step.text_content            │
│     → SSE: text { delta: "...", stepId: "provisioning-wifi" }          │
│                                                                       │
│  7. message.part.updated { part.type=tool, tool=task, status=completed }│
│     → task_agent_map 弹出 → flush pending → step_end                   │
│     → SSE: step_end { stepId: "provisioning-wifi" }                    │
│                                                                       │
│  8. message.part.updated { part.type=text, part.sessionID=MAIN }      │
│     → routing_agent=None → agg.content                                 │
│     → SSE: text { delta: "WiFi 仿真已完成..." }                        │
│                                                                       │
│  9. session.idle { sessionID=MAIN }                                    │
│     → SSE: done { messageId, tokens... }                               │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

**关键问题**：步骤 2 和 3 之间存在竞态窗口。如果 3 先到达，`task_agent_map` 为空，`routing_agent` 为 None，SubAgent 内容被误判为 Orchestrator 内容。

---

## 5. Bridge 层（opencode_bridge.py）的关键差异

### 5.1 事件过滤逻辑差异

| 过滤维度 | Agno bridge (agent_bridge.py) | OpenCode bridge (opencode_bridge.py) |
|---------|-------------------------------|--------------------------------------|
| Session 过滤 | 无需过滤（agno 流绑定到单个 Team 实例） | 必须过滤（全局 /event 端点混合所有 session） |
| 子会话事件 | agno 内部路由，bridge 无感 | **必须放行**子会话事件（`part.sessionID != sid`） |
| User echo | agno 不会回显 user 消息 | OpenCode 会回显 user 消息的 TextPart，需过滤 |
| 连接时序 | 同步调用 `team.arun()` | 必须**先建立 SSE 连接，再发 prompt**，否则丢失早期事件 |

### 5.2 当前 Bridge 的已知问题

**问题 A：Session 过滤遗漏子会话事件**

```python
# 旧版设计文档中的过滤逻辑（有 bug）：
event_session = (
    props.get("sessionID")
    or props.get("info", {}).get("sessionID")
    or (props.get("part", {}) or {}).get("sessionID")  # ← 这行会错误过滤子会话事件
)
if event_session and event_session != sid:
    continue  # ← 子会话事件被丢弃！
```

**现版修复**：不使用 `part.sessionID` 做过滤，只用 `props.sessionID` 和 `props.info.sessionID`。子会话的 `part.sessionID` 用于适配层的路由判断，不用于过滤。

**问题 B：User 消息 echo**

OpenCode 在子会话中会创建 user 类型的消息（Task tool 的任务描述），这些消息的 TextPart 会通过 `/event` 流发出。如果不过滤，会被当作 SubAgent 的文本输出。

**修复方式**：适配器追踪 `user_message_ids`（从 `message.updated(role=user)` 提取），在 text Part 处理时跳过。

---

## 6. Adapter 层对比：事件映射全景

### 6.1 Agno event_adapter.py 事件处理一览

| Agno 事件 | 条件 | SSE 输出 | 状态更新 |
|-----------|------|----------|----------|
| `TeamReasoningContentDelta` | leader=True | `thinking {delta}` | `agg.thinking_content += delta` |
| `ReasoningContentDelta` | leader=False | `thinking {delta, stepId}` | `step.pending_thinking += delta` |
| `ToolCallStarted(delegate_task_to_member)` | leader=True | `step_start {stepId, title}` | 创建 StepAggregate，注册 steps_by_id |
| `ToolCallStarted(get_skill_script)` | leader=False | （无 SSE） | 记录开始时间，缓存 call args |
| `ToolCallStarted(get_skill_instructions/reference)` | leader=False | （无 SSE） | 记录开始时间 |
| `ToolCallCompleted(get_skill_script)` | leader=False | `sub_step` + `wifi_result`/`render`/`report` | flush pending → step.items |
| `ToolCallCompleted(delegate_task_to_member)` | leader=True | `step_end {stepId}` | （不从 steps_by_id 移除） |
| `RunContent` | leader=True | `text {delta}` | `agg.content += delta` |
| `RunContent` | leader=False | `text {delta, stepId}` | `step.text_content += delta` |
| `ModelRequestCompleted` | any | （无 SSE） | 累加 token 统计 |
| `RunCompleted` | leader=True | `done {...}` | `agg.status = "done"` |
| `RunCompleted` | leader=False | （无 SSE） | flush member text |
| `RunError` | any | `error {message}` | `agg.status = "error"` |

### 6.2 OpenCode opencode_adapter.py 事件处理一览

| OpenCode 事件 | Part 类型 | 条件 | SSE 输出 | 与 Agno 差异 |
|--------------|-----------|------|----------|-------------|
| `message.part.updated` | reasoning | sessionID==MAIN | `thinking {delta}` | ✅ 对齐 |
| `message.part.updated` | reasoning | sessionID!=MAIN | `thinking {delta, stepId}` | ⚠️ 依赖 routing_agent 推断 |
| `message.part.updated` | tool(task, running) | — | 注册 task_agent_map | ⚠️ **Agno 无等价物**（Agno 用 delegate_task_to_member） |
| `message.part.updated` | tool(task, completed) | — | `step_end {stepId}` | ⚠️ 需要 flush pending |
| 首条子会话事件 | any | sessionID!=MAIN + routing_agent 首次出现 | `step_start` | ⚠️ **延迟触发**（Agno 是即时触发） |
| `message.part.updated` | text | sessionID==MAIN | `text {delta}` | ✅ 对齐 |
| `message.part.updated` | text | sessionID!=MAIN | `text {delta, stepId}` | ⚠️ 需过滤 user echo |
| `message.part.updated` | tool(get_skill_*, completed) | — | `sub_step` + renders | ⚠️ stdout 格式需包装（Bug1） |
| `message.part.updated` | step-finish | — | `step_end` or token 累加 | ⚠️ 与 task.completed 可能重复 |
| `message.updated` | completed | — | `done`（备选终止） | ⚠️ 与 session.idle 重复 |
| `session.idle` | — | sessionID==MAIN | `done` | ✅ 主终止信号 |
| `session.error` | — | — | `error` | ✅ 对齐 |

### 6.3 缺失映射（OpenCode 适配器尚未覆盖）

| 功能 | Agno 实现 | OpenCode 现状 | 影响 |
|------|----------|--------------|------|
| **Observability Tracer** | 每个事件同步写 traces/tool_calls/messages | 完全缺失 | sessions.db 无 OpenCode 会话数据 |
| **member RunCompleted flush** | `RunCompleted(leader=False)` 触发 flush member text + trace | 无等价事件处理 | 最后一段 member 文本可能丢失 |
| **图片路径处理** | `_handle_wifi_images()` 拷贝图片到 `data/images/` | 未实现 | WiFi 热力图无法在前端显示 |
| **finally 兜底 flush** | thinking buffer + member text buffer 兜底 flush | 部分实现 | 异常退出时数据可能不完整 |
| **多 SubAgent 并发** | `steps_by_id` 注册表支持多 member 交织 | `task_agent_map` + `current_agent` 单一活跃 | 同时委派多个 SubAgent 时只有最后一个正确 |

---

## 7. 对齐修复方案

### 7.1 P0：事件顺序保障（根因3 修复）

**问题**：task tool running 和子会话首条事件无因果序，导致 step_start 可能延迟或缺失。

**方案**：引入事件缓冲队列机制。

```
当 part.sessionID != main_session_id 且 routing_agent 为 None 时：
  → 将该事件暂存到 pending_events[part.sessionID] 队列
  → 当后续 task.running 到达并注册 task_agent_map 后
  → 检查所有 pending_events，回放属于该 subagent_type 的缓冲事件
```

伪代码：

```python
# 新增缓冲区
pending_sub_events: dict[str, list[dict]] = {}  # sub_sessionID → [event, ...]
sub_session_to_agent: dict[str, str] = {}        # sub_sessionID → agent_type

# 在 task tool running 时：
if tool_name == "task" and status == "running":
    subagent_type = state["input"]["subagent_type"]
    task_agent_map[call_id] = subagent_type
    # 检查是否有该 agent 的缓冲事件需要回放
    for sub_sid, events in list(pending_sub_events.items()):
        if sub_sid not in sub_session_to_agent:
            # 首个 pending 子会话可能就是这个 agent 的
            sub_session_to_agent[sub_sid] = subagent_type
            for evt in events:
                # 回放，使用正确的 routing_agent
                yield from _process_event(evt, routing_agent=subagent_type)
            del pending_sub_events[sub_sid]

# 在处理子会话事件时：
if part_session != main_session_id and routing_agent is None:
    # 还不知道归属，缓冲
    pending_sub_events.setdefault(part_session, []).append(event)
    continue
```

### 7.2 P0：render 事件全路径验证

**问题**：`_emit_renders()` 的 stdout 包装修复后，需逐个 skill 验证输出格式。

**方案**：为每个 skill 建立端到端测试用例。

| Skill | stdout 格式 | _parse_stdout 期望 | 需验证 |
|-------|------------|-------------------|--------|
| wifi_simulation | JSON 对象（含 heatmap_data, images） | `{"stdout": "<json>"}` | ✅ _emit_renders 已包装 |
| experience_assurance | JSON 对象 | `{"stdout": "<json>"}` | ✅ _emit_renders 已包装 |
| insight_query | JSON 对象（含 results, chart_configs） | `{"stdout": "<json>"}` | ✅ _emit_renders 已包装 |
| insight_report | Markdown 文本 | 直接使用 | ⚠️ 需确认是否走 _emit_renders |
| insight_nl2code | JSON/文本 | `{"stdout": "..."}` | ⚠️ 需确认 |

### 7.3 P1：多 SubAgent 并发支持

**问题**：当前 `task_agent_map` 使用 `next(iter(...))` 取第一个值作为 `routing_agent`，无法处理多个 SubAgent 同时活跃。

**方案**：引入 `sub_session_to_agent` 映射表。

```python
# 新增映射表
sub_session_to_agent: dict[str, str] = {}  # sub_sessionID → agent_type

# 在 task tool running 时，记录子会话 → agent 映射
# （需要从 OpenCode 事件中找到子会话 ID 与 task callID 的关联）

# 在路由时：
if part_session != main_session_id:
    routing_agent = sub_session_to_agent.get(part_session)
```

**难点**：OpenCode 的 task tool running 事件中，`state.input` 包含 `subagent_type`，但不包含子会话 ID。子会话 ID 只在子会话的事件的 `part.sessionID` 中出现。需要通过时序关联（task.running 后紧接的新 sessionID 事件）来建立映射。这也是上面 P0 缓冲队列方案要解决的核心关联问题。

### 7.4 P1：Observability 对齐

**问题**：OpenCode 通道完全缺失 Tracer 集成，sessions.db 无记录。

**方案选择**：

| 方案 | 工作量 | 效果 |
|------|--------|------|
| A. 在 opencode_adapter 中注入 Tracer 调用 | 中 | 两个引擎的 sessions.db 格式一致 |
| B. 依赖 OpenCode 自带的 observability | 低 | 数据在不同 SQLite 中，需要两套查看工具 |
| C. 两者并行：Tracer 做基本记录，详细数据走 OpenCode | 中高 | 最佳可观测性 |

**推荐方案 B（短期）+ A（中期）**：短期先利用 OpenCode 的 TUI/CLI 调试，中期在适配器中注入 Tracer 调用以统一监控视图。

### 7.5 P2：图片路径处理

**问题**：WiFi 仿真产出的 PNG 图片在 OpenCode 通道下路径不同。

**方案**：在 `_emit_renders()` 中复用 `_handle_wifi_images()` 的拷贝逻辑。

```python
# opencode_adapter.py 的 _emit_renders() 中追加：
if skill_name == "wifi_simulation" and results:
    # 从 stdout JSON 中提取图片路径，拷贝到 data/images/
    from api.event_adapter import _handle_wifi_images
    _handle_wifi_images(parsed_stdout)
```

### 7.6 P2：终止信号去重

**问题**：`session.idle` 和 `message.updated(completed)` 可能都触发 done。

**方案**：状态机守卫。

```python
if agg.status == "done":
    return  # 已经发过 done，不重复
agg.status = "done"
yield format_sse("done", {...}), agg
return
```

**现状**：代码中已在 `session.idle` 处理中检查 `agg.status == "streaming"`，但 `message.updated(completed)` 分支也需要同样的守卫。

---

## 8. 测试验证矩阵

| 测试场景 | 验证点 | Agno 期望 | OpenCode 期望 | 当前状态 |
|---------|--------|-----------|--------------|---------|
| 简单问候（"你好"） | thinking → text → done | ✅ | ✅ | 基本正常 |
| WiFi 仿真 | thinking → step_start → sub thinking → sub_step → wifi_result → step_end → text → done | ✅ | ❌ 顺序乱 | 需修复 P0 |
| 网络覆盖分析 | thinking → step_start(insight) → 多 sub_step → report/render → step_end → text → done | ✅ | ❌ 报告缺失 | 需修复 P0 + render |
| 多 Agent 委派 | 多个 step_start → 交织执行 → 各自 step_end → 总结 | ✅ | ❌ 只有最后一个 | 需修复 P1 |
| 错误处理 | error SSE 事件正确触发 | ✅ | ⚠️ 部分覆盖 | 需补充 |
| Token 统计 | done 事件包含准确 token 数 | ✅ | ⚠️ 可能双重计 | 需验证 Bug6 |

---

## 9. 实施优先级与路线图

```
P0（阻塞性，必须修复才能基本可用）:
  ├─ 事件缓冲队列机制（解决 step_start 延迟/缺失）
  ├─ render 事件全路径验证（解决报告/图表缺失）
  └─ 终止信号去重（解决 done 重复或缺失）

P1（功能性，影响多场景可用性）:
  ├─ 多 SubAgent 并发支持（sub_session_to_agent 映射）
  ├─ Observability Tracer 集成
  └─ User echo 过滤健壮性

P2（完善性，提升体验）:
  ├─ 图片路径处理
  ├─ Finally 兜底 flush 补全
  └─ Token 统计准确性验证
```

---

## 10. 附录：文件清单与职责对照

| 文件 | Agno 通道职责 | OpenCode 通道职责 | 共享/独立 |
|------|-------------|-----------------|----------|
| `api/routes/messages.py` | 路由到 agno adapter | 路由到 opencode adapter | 共享（引擎分发逻辑） |
| `api/agent_bridge.py` | 管理 Team 实例 + session | — | Agno 独有 |
| `api/event_adapter.py` | agno 事件 → SSE 转译 | 提供 MessageAggregate/StepAggregate 类 + render 辅助函数 | 类定义共享，逻辑独立 |
| `api/opencode_bridge.py` | — | 管理 OpenCode session + SSE 消费 | OpenCode 独有 |
| `api/opencode_adapter.py` | — | OpenCode 事件 → SSE 转译 | OpenCode 独有 |
| `api/engine_config.py` | — | — | 共享（引擎选择） |
| `api/sse.py` | SSE 格式编码 | SSE 格式编码 | 共享 |
| `api/routes/engine.py` | — | — | 共享（配置 API） |
| `core/agent_factory.py` | 构建 agno Team | — | Agno 独有 |
| `core/session_manager.py` | 管理 agno session | — | Agno 独有 |
