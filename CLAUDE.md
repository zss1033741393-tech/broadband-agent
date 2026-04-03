# 家宽体验感知优化 Agent 智能体

家庭宽带用户体验优化的 Agent Pipeline 原型。用户输入意图 → 解析追问 → 基于 JSON 模板填充方案 → 约束校验 → NL2JSON 配置输出。
设计文档参见@design.md 文件。

## 技术栈

- Python 3.11+, FastAPI, Gradio
- Agent 框架: Agno (pip install agno)
- LLM: OpenAI API 兼容格式（可对接内部开源模型）
- 存储: SQLite (aiosqlite)
- 配置: YAML (configs/), 敏感信息在 .env

## 命令

- `uvicorn app.main:app --reload` — 启动 FastAPI 开发服务器
- `ruff check .` — 代码检查
- `ruff format .` — 代码格式化
- `pytest tests/` — 运行测试
- `pytest tests/test_agents/test_intent_agent.py -v` — 运行单个测试文件

## 项目结构

- `app/agents/` — 4 个 Stage Agent (intent_agent, plan_agent, constraint_agent, config_agent) + pipeline.py 编排
- `app/tools/` — Tool 函数，每个 Agent 对应一组 Tools
- `app/models/` — Pydantic 数据模型 (IntentGoal, Plan, Config)
- `app/config.py` — 多模型 LLM 配置加载，按 Stage 从 configs/llm.yaml 读取，fallback 到 default
- `app/logger/` — 结构化日志，Pipeline 日志格式: `[时间] [Stage] [Component] [Level] 消息`
- `app/db/` — SQLite CRUD
- `app/api/` — FastAPI 路由
- `skills/` — Markdown 格式的 Skills 文件，按 stage1~stage4 分目录，运行时渐进式加载到 Agent instructions
- `templates/` — 6 个预定义 JSON 模板 (用户画像 + 五大方案)，是方案生成的基线配置
- `configs/` — YAML 配置: llm.yaml (多模型), pipeline.yaml (运行参数), logging.yaml (日志)
- `ui/chat_ui.py` — Gradio 对话调试界面

## 核心架构概念

**Pipeline 4 阶段流转**:
Stage1 意图解析 → Stage2 方案生成(模板填充) → Stage3 约束校验 → Stage4 配置输出(NL2JSON)。Stage3 不通过时回退 Stage2，最多重试 3 次。

**Skills + Tools 互补**: Skills 是 Markdown 文件，注入 Agent 的 instructions 提供领域知识和决策规则。Tools 是 Python 函数，执行具体操作。每个 Stage 只加载当前阶段的 Skills，避免 context 爆 token。

**方案生成不是从零生成**: templates/ 下有预定义 JSON 模板（含默认阈值），Agent 根据意图目标决定哪些字段需要修改，填充/调整参数值。本质是模板渲染 + 条件决策。

**多模型配置**: 不同 Stage 可用不同模型。Stage1/4 建议强模型（语义理解、结构化输出），Stage2/3 可用轻量模型。配置在 configs/llm.yaml，API Key 在 .env。

## 代码规范
**Python**
- 遵循 PEP8，使用 `async/await`，类型注解可选但建议
- 注释用中文，复杂逻辑才加注释。
- 所有函数必须有类型标注
- 数据校验用 Pydantic Model，不要用裸 dict 传递结构化数据
- Tool 函数必须写 docstring，说明输入输出
- 格式化用 ruff，不要手动调格式
- 文件名 snake_case，类名 PascalCase，Agent 名称英文 PascalCase (IntentParser, PlanFiller, ConstraintChecker, ConfigTranslator)
- 异步优先: FastAPI 路由和 DB 操作用 async/await

## 日志规范

- 使用 `app.logger.get_logger(stage, component)` 获取 logger，不要用 print 或裸 logging
- 使用 `app.logger.log_step(logger, action)` 上下文管理器自动记录耗时
- LLM 调用必须记录 model、tokens_in、tokens_out、latency_ms
- 日志输出到 logs/app.log (应用) 和 logs/pipeline.log (Pipeline 追踪)

## Git 规范

- Commit 格式: `<type>: <description>`
- type 取值: feat, fix, refactor, docs, skill, tmpl
- 分支: main (稳定) + dev (开发)
- **push 规则（重要）**：
  - 必须使用 `git push -u origin <branch>` 通过 PAT URL 直接推送
  - **严禁使用 GitHub MCP Server 工具（mcp__github__push_files 等）提交代码**，速度极慢
  - 如果 `git push origin` 失败，检查 remote URL 是否仍为 PAT URL（`git remote get-url origin`）
  - 推送后执行 `git fetch origin <branch>:refs/remotes/origin/<branch>` 同步本地跟踪引用，避免 stop-hook 误报
- 禁止 --force 到 main/master

## 注意事项

- IMPORTANT: 不要修改 templates/ 下的 JSON 模板文件结构，除非明确要求。这些是方案基线配置
- IMPORTANT: skills/ 下的 Markdown 文件每个控制在 1000-2000 字以内，过长会影响模型指令遵循
- IMPORTANT: .env 只放敏感信息 (API Key)，模型参数、Pipeline 参数走 configs/*.yaml
- 新增 Tool 函数后在 tests/test_tools/ 下补测试
- SQLite 数据库文件路径由 .env 中 SQLITE_DB_PATH 指定，默认 ./data/agent.db
- 禁止将项目中的设计文档design.md和需求文档提交到git。

## 领域术语

- **CEI**: Customer Experience Index，用户体验指数
- **NCE**: Network Cloud Engine，网络云引擎
- **NL2JSON**: Natural Language to JSON，自然语言转配置
- **感知粒度**: 体验指标的采集精度（采样间隔、聚合窗口等）
- **闭环**: 从发现问题到解决问题的完整处置流程
- **稽核**: 闭环操作后的效果审计和回滚机制
- **APPflow**: 应用流量识别和管控策略
