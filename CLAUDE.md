# CLAUDE.md

## 项目概述

家宽体验感知优化 Agent。Agno 原生 Skills + Knowledge + Guardrails + AgentOS + Structured Output + Streaming。

核心模式：**运行时 Skill 发现 → 渐进式加载 → 自主链路决策**。

## 技术栈

Python 3.11+, Agno, Gradio, SQLite, LanceDB

## Agno 能力使用

| 能力 | 用法 |
|------|------|
| Skills | 自动扫描 skills/ 发现，元工具 list/get/run |
| Agent Loop | max_turns=15 自主循环 |
| Structured Output | response_model=Pydantic 强制格式 |
| Streaming | run_stream() 实时流到前端 |
| Guardrails | PromptInjection 输入 + ConfigOutput 输出校验 |
| Knowledge | LanceDB 向量存储，领域知识 RAG 检索 |
| Memory | session 对话历史。跨会话记忆 P1，用户系统就绪后启用 |
| AgentOS | 替代手写 FastAPI + Tracer，原生 API + trace + Web UI |
| Tracing | debug_mode=True + AgentOS UI 可视化 |

## 项目结构

```
broadband-agent/
├── configs/
│   ├── llm.yaml              # 模型注册（含 api_key）
│   ├── pipeline.yaml         # 运行参数
│   └── logging.yaml
├── app/
│   ├── main.py               # AgentOS 入口 + Gradio 挂载
│   ├── config.py             # YAML 加载
│   ├── agent/
│   │   └── agent.py          # Agent 定义（全部 Agno 能力集成）
│   ├── models/               # Pydantic 结构化输出
│   │   ├── intent.py         # IntentGoal
│   │   ├── plan.py           # PlanResult
│   │   ├── constraint.py     # ConstraintResult
│   │   └── config.py         # ConfigOutput
│   ├── guardrails.py         # 自定义输出护栏
│   ├── db/
│   └── logger/
├── skills/                   # 自包含 Skills（自动扫描）
│   ├── intent_parser/        # SKILL.md + scripts/
│   ├── user_profiler/        # SKILL.md + scripts/ + references/
│   ├── plan_generator/       # SKILL.md + scripts/ + references/(5模板)
│   ├── constraint_checker/   # SKILL.md + scripts/ + references/(规则)
│   ├── config_translator/    # SKILL.md + scripts/ + references/(schema)
│   └── domain_expert/        # SKILL.md + references/(知识→灌入Knowledge)
├── ui/chat_ui.py             # Gradio 调试界面
├── data/
│   ├── agent.db              # SQLite
│   └── lancedb/              # Knowledge 向量存储
├── logs/
└── tests/
```

## Agent 核心代码

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.skills import Skills, LocalSkills
from agno.memory import Memory
from agno.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb
from agno.storage.agent.sqlite import SqliteAgentStorage
from agno.guardrails import PromptInjectionGuardrail
from agno.os import AgentOS
from app.config import load_config
from pathlib import Path

cfg = load_config()  # 全部从 configs/*.yaml 加载，零硬编码

def discover_skills(skills_dir: Path) -> Skills:
    loaders = []
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists():
            loaders.append(LocalSkills(str(child)))
    return Skills(loaders=loaders)

agent = Agent(
    model=OpenAIChat(id=cfg.llm.model, api_key=cfg.llm.api_key, base_url=cfg.llm.base_url),
    skills=discover_skills(Path(cfg.pipeline.skills_dir)),
    knowledge=Knowledge(vector_db=LanceDb(table_name=cfg.storage.lancedb_table, uri=cfg.storage.lancedb_uri)),
    instructions=SYSTEM_PROMPT,
    memory=Memory(),
    add_history_to_context=True,
    num_history_runs=cfg.pipeline.num_history_runs,
    # enable_memories=True,          # P1: 用户系统就绪后启用
    storage=SqliteAgentStorage(table_name=cfg.storage.sqlite_table, db_file=cfg.storage.sqlite_db_path),
    pre_hooks=[PromptInjectionGuardrail()],
    max_turns=cfg.pipeline.max_turns,
    reasoning=cfg.pipeline.reasoning,
    debug_mode=cfg.pipeline.debug_mode,
)

agent_os = AgentOS(agents=[agent], tracing=True)
app = agent_os.get_app()
```

## 关键设计决策

1. **Skills 自动扫描**：扫描 skills/ 下所有含 SKILL.md 的子目录，不硬编码路径
2. **Agent 自主决策**：不编排 Pipeline，system prompt 只提供流程指导
3. **Skill 自包含**：模板、脚本、参考资料都在 Skill 内部
4. **Skill 与模型解耦**：模型在 Agent 级注册，SKILL.md 不声明模型
5. **Structured Output**：Skill 输出用 Pydantic response_model 强制约束
6. **Streaming**：run_stream() 流式输出，思考过程实时可见
7. **Guardrails**：输入防注入 + 输出 schema 校验
8. **Knowledge RAG**：领域知识灌入 LanceDB，语义检索替代文件读取
9. **User Memory**：P1，用户系统就绪后启用 enable_memories
10. **AgentOS**：替代手写 FastAPI/Tracer，原生 API + trace + Web UI
11. **所有配置在 YAML**：configs/llm.yaml 含 api_key，没有 .env
12. **阶段产出物持久化**：四个阶段产出（意图/画像/方案/配置）需写入 `outputs/` 供下游系统消费，见"架构演进计划"
13. **Skills 与会话解耦**：脚本层不感知 session_id，产出物写入由 app 层负责（通过 AgentOS post-hook 或独立 OutputSink）

## 架构演进计划

### P1 — 阶段产出物持久化（下游交付）

**背景**：四个阶段产出物（intent / profile / plans / configs）目前仅存在于 Agent context 和 AgentOS trace 中，无法直接交付给下游系统（如配置下发平台、数据分析系统）。

**设计原则**：
- Skills 脚本保持纯 stdout，不感知 session 或文件路径（职责分离）
- 持久化逻辑在 app 层实现，不侵入 Skills

**推荐实现**（待调研 AgentOS hook API 后确认）：
```
app/outputs/
├── sink.py          # OutputSink: 监听 tool call 结果，按阶段写文件
└── router.py        # FastAPI 路由: GET /outputs/{session_id}/{stage}
```
产出物路径：`outputs/{session_id}/{stage}.json`（intent / profile / plans / configs）
下游系统通过 REST API 按 session_id 拉取，或订阅文件变更。

**阻塞点**：需确认 AgentOS 是否暴露 tool call 完成的 post-hook 接口。

### P2 — 上下文感知压缩（长对话）

**背景**：约束校验重试循环（最多 3 次）会导致单次 run 内 tool call 结果堆积，context 膨胀影响模型决策质量。

**设计思路**：监控当前 run 的 token 计数，超过阈值时将早期 tool 结果卸载到文件，context 中替换为占位符（`已归档: outputs/{session_id}/plans.json`），模型按需调用 `get_skill_reference` 读取。

**现状**：Agno 暂无原生支持；当前链路最多 15 次工具调用，实际未触发瓶颈，暂不实现。待真实负载压测后评估。

## Commit 规范

```
feat: 新功能
fix: 修复
refactor: 重构
docs: 文档
skill: Skills 变更（SKILL.md / scripts / references）
```

**README 同步规则（重要）**：
每次提交如果涉及以下内容，**必须同步更新 README.md**：
- 新增或删除功能模块（如新增 OutputSink、新增 API 端点）
- 流程或架构变更（如 Agent 决策流程、Skills 机制变化）
- 项目结构变化（如新增目录 `app/outputs/`）
- 配置参数变更（如新增 `tool_hooks`、修改 pipeline 参数）

README 不需要因为 bug fix、测试补充、注释修改而更新。

- **push 规则（重要）**：
  - 必须使用 `git push -u origin <branch>` 通过 PAT URL 直接推送
  - **严禁使用 GitHub MCP Server 工具（mcp__github__push_files 等）提交代码**，速度极慢
  - 如果 `git push origin` 失败，检查 remote URL 是否仍为 PAT URL（`git remote get-url origin`）
  - 推送后执行 `git fetch origin <branch>:refs/remotes/origin/<branch>` 同步本地跟踪引用，避免 stop-hook 误报
- 禁止 --force 到 main/master

## 常用命令

```bash
pip install "agno[openai,lancedb]" gradio pyyaml ruff
uvicorn app.main:app --reload --port 8000
# AgentOS UI: http://localhost:8000
# Gradio 调试: http://localhost:8000/gradio
pytest tests/ -v
ruff check --fix . && ruff format .
```

## 注意事项

- 详细设计见 design.md（**设计文档只在本地维护，禁止提交到 git**）
- **禁止将 `design.md` 或任何设计/原型文档提交到版本库**，此类文档仅供本地参考
- **零硬编码**：所有配置从 configs/*.yaml 读取，通过 `load_config()` 统一加载
- **追问交互**：intent_parser 返回 needs_clarification=true 时 Agent 必须暂停追问用户，不猜测
- **画像补全**：user_profiler 返回 has_complete_profile=false 时，能推断的补全、关键字段追问、非关键用默认值
- **memory 优先**：用户历史画像中已有的字段不追问，直接使用
- **约束校验警告**：severity=warning 必须告知用户并等待确认
- 不要建 app/tools/ 或顶层 templates/ 目录
- 不要写 skill_loader.py 或 tracer.py，Agno 原生处理
- 不要在 SKILL.md 里加模型相关字段
- SKILL.md 的 description 要精准（Agent 靠它决定是否加载）
- SKILL.md 的"后续建议"引导 Agent 决策链路
- constraint_checker 是强制步骤，system prompt 中明确标注
- domain_expert 的文本类知识灌入 Knowledge，结构化数据留 references/
