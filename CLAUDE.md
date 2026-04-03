# CLAUDE.md

## 项目概述

家宽体验感知优化 Agent 智能体原型。通过 Agno 框架构建 Skills 驱动的 Agent，实现用户意图到设备配置的端到端自动化生成。

核心架构：**Agent 自主决策 + Skills 渐进式加载**。Agent 根据用户输入和上下文自主选择调用哪个 Skill，system prompt 只提供流程指导（建议顺序），不做硬编排。

## 技术栈

- Python 3.11+
- Agno（Agent 框架，原生 Skills 支持）
- FastAPI（后端）
- Gradio（对话调试界面）
- SQLite（会话/配置持久化）
- LLM：OpenAI API 兼容格式（可对接内部开源模型）

## 项目结构

```
broadband-agent/
├── configs/                         # YAML 配置（含 API Key，不拆 .env）
│   ├── llm.yaml                     # 模型注册
│   ├── pipeline.yaml                # 运行参数
│   └── logging.yaml                 # 日志配置
├── app/                             # FastAPI 后端
│   ├── main.py                      # 入口 + Gradio 挂载
│   ├── config.py                    # 配置加载
│   ├── agent/                       # Agent 核心
│   │   ├── agent.py                 # Agno Agent 定义 + system prompt
│   │   ├── skill_loader.py          # Skills 发现与注册
│   │   └── tracer.py                # Agent 轨迹记录
│   ├── models/                      # Pydantic 数据模型
│   ├── db/                          # SQLite
│   ├── logger/                      # 日志模块
│   └── api/                         # FastAPI 路由
├── skills/                          # 自包含 Skills（核心，详见下方）
├── ui/                              # Gradio 界面
│   └── chat_ui.py
├── traces/                          # Agent 轨迹（按 session_id 隔离）
├── logs/
└── outputs/
```

## Skills 架构（最重要）

每个 Skill 是自包含的能力包，与模型无关：

```
skills/{skill_name}/
├── SKILL.md              # frontmatter(name + description) + 何时使用 + 处理步骤 + 规则
├── scripts/              # Python 执行脚本
│   └── handler.py
└── references/           # JSON 模板、规则文档、示例
    └── template.json
```

关键原则：
- **Skill 内聚**：模板在 `references/`，脚本在 `scripts/`，不放外部目录
- **Skill 与模型无关**：SKILL.md 里只有 name + description，不声明模型
- **模型是 Agent 级配置**：在 `configs/llm.yaml` 注册，创建 Agent 时绑定
- **新增 Skill**：只需在 `skills/` 下新建目录 + SKILL.md，不改任何配置文件

现有 6 个 Skills：
- `intent_parsing` — 意图解析与追问
- `user_profile` — 用户画像补全
- `plan_filling` — 五大方案模板填充（模板在 references/ 内）
- `constraint_check` — 约束校验（性能/组网/冲突）
- `config_translation` — NL2JSON 配置转译
- `domain_knowledge` — 领域知识（仅参考资料，无脚本）

## Agent Trace 轨迹

每次会话保存到 `traces/{session_id}/`：
- `trace.jsonl` — 每步一行 JSON（user_input / agent_thinking / skill_load / skill_execute / agent_output）
- `artifacts/` — 各阶段输出物（intent_goal.json / plans/*.json / constraint_result.json / configs/*.json）
- `conversation.json` — 完整对话记录

## 常用命令

```bash
# 安装依赖
pip install agno fastapi uvicorn gradio pydantic openai pyyaml aiosqlite ruff

# 启动服务
uvicorn app.main:app --reload --port 8000

# 代码格式化
ruff check --fix .
ruff format .

# 运行测试
pytest tests/
```

## 代码规范

- 遵循 PEP8，使用 `async/await`，类型注解可选但建议
- 所有函数必须有类型标注
- 使用 Pydantic Model 做数据校验
- 文件名 `snake_case.py`，类名 `PascalCase`，Skill 目录名 `snake_case`
- Skill 的 SKILL.md 必须有 frontmatter（name + description）
- 关键决策逻辑写中文注释，脚本函数写 docstring
- 使用 `ruff` 格式化

## 日志规范

日志标签格式 `[Skill:xxx]`：

```
[2026-04-03 14:23:01] [Skill:intent_parsing] [INFO] Agent 加载 Skill
[2026-04-03 14:23:02] [Skill:intent_parsing] [DEBUG] LLM 调用 | model=gpt-4o | tokens_in=520
[2026-04-03 14:23:15] [Skill:constraint_check] [WARN] 校验失败 | conflict="节能时段与保障时段冲突"
```

## Commit 规范

```
feat: 新功能
fix: 修复
refactor: 重构
docs: 文档
skill: Skills 变更（SKILL.md / scripts / references）
```
- **push 规则（重要）**：
  - 必须使用 `git push -u origin <branch>` 通过 PAT URL 直接推送
  - **严禁使用 GitHub MCP Server 工具（mcp__github__push_files 等）提交代码**，速度极慢
  - 如果 `git push origin` 失败，检查 remote URL 是否仍为 PAT URL（`git remote get-url origin`）
  - 推送后执行 `git fetch origin <branch>:refs/remotes/origin/<branch>` 同步本地跟踪引用，避免 stop-hook 误报
- 禁止 --force 到 main/master

## 关键设计决策

1. **不是 Pipeline 编排**：Agent 自主决策调用哪个 Skill，system prompt 只提供流程指导
2. **Skill 自包含**：模板、脚本、参考资料都在 Skill 目录内，不放外部
3. **Skill 与模型解耦**：Skill 不声明模型需求，模型在 Agent 级别注册
4. **所有配置在 YAML**：`configs/llm.yaml` 包含 API Key，没有 `.env` 文件
5. **Agent Trace**：每次会话完整轨迹保存，包含思考过程、Skill 调用、输出物
6. **Gradio 三栏布局**：左边对话（含思考过程折叠）、右上输出物面板、右下 Trace 面板

## 注意事项

- 详细设计见 `design.md`（**设计文档只在本地维护，禁止提交到 git**）
- **禁止将 `design.md` 或任何设计/原型文档提交到版本库**，此类文档仅供本地参考
- 不要在 Skill 外部建 `tools/` 或 `templates/` 目录
- 不要在 SKILL.md 里加 model_tier 或任何模型相关字段
- plan_filling 的 5 个模板可并行填充（asyncio.gather）
- 约束校验失败时 Agent 自主决策回退，不是硬编码循环
- config_translation 是独立 Agent 子任务（NL2JSON/NL2DSL）
