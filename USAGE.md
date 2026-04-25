# Token 用量查询手册

数据库路径：`data/sessions.db`（observability 库，同步写入 JSONL `data/logs/trace/YYYY-MM-DD.jsonl`）

```bash
sqlite3 data/sessions.db
```

---

## 1. 查当前有哪些会话

```sql
SELECT id, session_hash, created_at, ended_at, task_type
FROM sessions
ORDER BY created_at DESC
LIMIT 20;
```

---

## 2. 按 SubAgent 汇总某次会话的 token 用量

`llm_calls` = 该 Agent 在本次会话里独立调用 LLM 的次数。

```sql
SELECT
    agent_name,
    SUM(json_extract(payload_json, '$.input_tokens'))     AS input_tokens,
    SUM(json_extract(payload_json, '$.output_tokens'))    AS output_tokens,
    SUM(json_extract(payload_json, '$.total_tokens'))     AS total_tokens,
    SUM(json_extract(payload_json, '$.reasoning_tokens')) AS reasoning_tokens,
    COUNT(*)                                               AS llm_calls
FROM traces
WHERE event_type = 'llm_usage'
  AND session_id = <SESSION_ID>
GROUP BY agent_name
ORDER BY total_tokens DESC;
```

**典型输出说明**

| agent_name | 含义 |
|---|---|
| `orchestrator` | Team leader（意图识别 + 路由 + 汇总），coordinate 模式下每轮派发都调用一次 |
| `planning` | PlanningAgent，goal_parsing / plan_design / plan_review / plan_store 各占若干次 |
| `insight` | InsightAgent，Plan→Decompose→Execute→Reflect→Report 每阶段一次 |
| `provisioning-wifi` | ProvisioningWifiAgent |
| `provisioning-delivery` | ProvisioningDeliveryAgent |
| `provisioning-cei-chain` | ProvisioningCeiChainAgent |

---

## 3. 展示调用时序流（orchestrator → planning → orchestrator → provisioning-wifi …）

按时间展开每次 LLM 调用，直观看到各 Agent 的交替顺序和每步 token 消耗。

```sql
SELECT
    ROW_NUMBER() OVER (ORDER BY created_at)            AS seq,
    agent_name,
    json_extract(payload_json, '$.input_tokens')       AS input,
    json_extract(payload_json, '$.output_tokens')      AS output,
    json_extract(payload_json, '$.total_tokens')       AS total,
    json_extract(payload_json, '$.reasoning_tokens')   AS reasoning,
    substr(created_at, 12, 8)                          AS time
FROM traces
WHERE event_type = 'llm_usage'
  AND session_id = <SESSION_ID>
ORDER BY created_at;
```

> **为什么 orchestrator 的 input 会在某次突然变大？**  
> 每次 SubAgent 完成后，其工具调用结果被追加到消息历史；orchestrator 再次调用时把完整历史全部带入，input token 随之"滚雪球"增长。

---

## 4. 跨所有会话按 Agent 汇总

```sql
SELECT
    agent_name,
    SUM(json_extract(payload_json, '$.total_tokens'))  AS total_tokens,
    COUNT(*)                                            AS llm_calls
FROM traces
WHERE event_type = 'llm_usage'
GROUP BY agent_name
ORDER BY total_tokens DESC;
```

---

## 5. 查某次会话的完整 trace 事件列表

```sql
SELECT
    id,
    event_type,
    agent_name,
    substr(created_at, 1, 19) AS ts,
    substr(payload_json, 1, 120)  AS payload_preview
FROM traces
WHERE session_id = <SESSION_ID>
ORDER BY created_at;
```

常见 `event_type`：

| event_type | 含义 |
|---|---|
| `request` | 用户消息进入 |
| `llm_usage` | 单次 LLM API 调用的 token 计量（含 agent 字段） |
| `llm_prompt` | 发送给 LLM 的完整 messages + tools（由 inject_prompt_tracer 触发） |
| `thinking` | LLM 推理内容（reasoning token 段） |
| `tool_invoke` | Skill 调用开始 |
| `tool_result` | Skill 调用完成（含 latency_ms） |
| `member_content` | SubAgent 的文本回复 |
| `member_completed` | SubAgent 运行完成 |
| `response` | Team leader 最终回复（含本次会话累计 token 汇总） |
| `error` | 异常事件 |

---

## 6. 查 response 事件中记录的会话级 token 汇总（agno 引擎）

`response` 事件的 payload 里存有整次会话的累计 token（所有 Agent 合计）。

```sql
SELECT
    session_id,
    json_extract(payload_json, '$.input_tokens')     AS total_input,
    json_extract(payload_json, '$.output_tokens')    AS total_output,
    json_extract(payload_json, '$.total_tokens')     AS grand_total,
    json_extract(payload_json, '$.reasoning_tokens') AS total_reasoning,
    substr(created_at, 1, 19)                        AS ts
FROM traces
WHERE event_type = 'response'
ORDER BY created_at DESC
LIMIT 20;
```

---

# OpenCode 引擎使用手册

FastAPI 后端支持 **agno**（默认）和 **OpenCode** 双引擎运行时切换，前端 SSE 协议完全不变。

## 7. 启动 OpenCode 引擎

### 7.1 前置条件

```bash
# 确认 opencode CLI 已安装
opencode --version

# 确认项目根目录存在 opencode.json（OpenCode agent 配置）
ls opencode.json
```

### 7.2 完整启动流程（双引擎模式）

```bash
# 终端 1 — 启动 OpenCode Server（必须在项目根目录，读取 opencode.json 和 skills/）
cd /path/to/broadband-agent
opencode serve --port 4096
# 预期输出: OpenCode server listening on http://127.0.0.1:4096

# 终端 2 — 启动 FastAPI 后端
cd /path/to/broadband-agent
uv run python -m api.main
# 预期输出: FastAPI 服务启动，端口 8080

# 终端 3 — 启动前端（broadband-agent-demo）
cd /path/to/broadband-agent-demo/frontend
npm run dev
# 预期输出: Local: http://localhost:5173
```

### 7.3 切换到 OpenCode 引擎

```bash
# 方式 1：API 切换（推荐）
curl -X PUT http://localhost:8080/api/engine \
  -H 'Content-Type: application/json' \
  -d '{"engine": "opencode", "opencode_url": "http://127.0.0.1:4096"}'

# 方式 2：直接编辑配置文件（FastAPI 无需重启，下次请求生效）
echo '{"engine": "opencode"}' > configs/engine.json

# 切回 agno
curl -X PUT http://localhost:8080/api/engine \
  -H 'Content-Type: application/json' \
  -d '{"engine": "agno"}'
```

### 7.4 验证连通性

```bash
# 1. OpenCode Server 健康检查
curl http://127.0.0.1:4096/global/health
# 期望: {"healthy":true,"version":"..."}

# 2. FastAPI 引擎状态
curl http://localhost:8080/api/engine
# 期望: {"code":0,"data":{"engine":"opencode","opencode_url":"http://127.0.0.1:4096",...}}

# 3. 通过 FastAPI 代理检查 OpenCode 连通性
curl http://localhost:8080/api/engine/health
# 期望: {"code":0,"data":{"engine":"opencode","healthy":true}}

# 4. 端到端发消息测试（需先创建会话）
curl -X POST http://localhost:8080/api/conversations/{conv_id}/messages \
  -H 'Content-Type: application/json' \
  -d '{"content": "你好"}' \
  --no-buffer
# 期望: SSE 流输出 event: text / event: done
```

---

## 8. OpenCode 调试

OpenCode 引擎有独立的 observability 体系，所有会话数据存储在 `~/.local/share/opencode/opencode.db`，通过 TUI 或 CLI 均可查看。

### 8.1 TUI 查看前端发送的对话历史

```bash
# 前提：opencode serve --port 4096 已在运行
opencode attach http://127.0.0.1:4096
```

进入 TUI 后按 `Leader + s` 打开 session 列表，可以看到所有通过前端发送的对话（标题格式为 `broadband-{conv_id[:8]}`）。选中任意 session 可查看：

- Orchestrator 的完整 reasoning（为什么路由给哪个 SubAgent）
- Task tool 委派的完整 payload
- 每个 `get_skill_script` 调用的 input 和 stdout
- SubAgent 的中间推理过程

> TUI 和前端可同时使用，互不干扰；也可在 TUI 里直接继续对话做单步调试。

### 8.2 跳转到指定 session

```bash
# conv_id → session_id 映射见 FastAPI 日志（opencode_bridge channel）
# 格式: "OpenCode session 创建: conv_id=xxx → sid=yyy"
opencode attach http://127.0.0.1:4096 --session <session-id>
```

### 8.3 CLI 导出与分析

```bash
# 列出所有 session
opencode session list

# 导出指定 session 的完整 JSON（含所有 Part、tool 调用）
opencode session export <session-id> > /tmp/debug.json

# 查看某次 session 里所有 get_skill_script 调用及其 stdout
cat /tmp/debug.json | jq '
  .messages[].parts[]
  | select(.type=="tool" and .tool=="get_skill_script")
  | {skill: .state.input.skill_name, status: .state.status, output: .state.output[:200]}'

# 查看 token 用量汇总
opencode stats
```

### 8.4 典型问题排查

| 现象 | 排查步骤 |
|---|---|
| 前端显示"工具调用出错" | 查 FastAPI 日志找 `conv_id` → 找对应 `session_id` → TUI 查看 tool Part 的 `state.error` |
| SubAgent 路由不正确 | TUI 里找 Orchestrator 的 reasoning Part，看路由决策逻辑 |
| insight 图表未渲染 | `session export` 后用 jq 确认 `insight_query` 的 stdout 是否含合法 `chart_configs` JSON |
| OpenCode Server 无响应 | `curl http://127.0.0.1:4096/global/health`，确认进程在项目根目录启动 |

### 8.5 注意事项

- `conv_id → session_id` 映射存在 FastAPI 进程内存中，**重启 FastAPI 后映射丢失**，同一 `conv_id` 会创建新的 OpenCode session（不影响功能，历史消息仍在 `data/api.db`）
- OpenCode session 数据独立存储，不写入 `data/sessions.db`（agno observability 库）
- `opencode serve` 必须在项目根目录启动，以便读取 `opencode.json` 和 `skills/` 目录
