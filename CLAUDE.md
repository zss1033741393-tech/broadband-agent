# CLAUDE.md

## 项目概述

家宽网络调优智能助手。基于 Agno 框架的单体 Agent，通过 9 个 Skills 覆盖从意图识别到配置下发的完整流程。

核心模式：**单 Agent + Skills 路由 → 三类任务分流 → 模板渲染 → Mock 下游**

## 技术栈

Python 3.11+、Agno ≥ 2.5.14、Gradio 4.x（Web UI）、SQLite（会话持久化）、Jinja2（模板渲染）、loguru（日志）

## 项目结构

```
├── configs/
│   ├── model.yaml          # 模型配置（provider / base_url / api_key / role_map）
│   ├── agent.yaml          # Agent 名称 + 启用的 Skills 列表 + memory 配置
│   ├── downstream.yaml     # 下游接口（mock/real 切换）
├── core/
│   ├── agent_factory.py    # 从 YAML 构造 Agent（model + skills + prompt + sqlite）
│   ├── model_loader.py     # 模型实例化 + prompt tracer 注入
│   ├── session_manager.py  # session_hash → Agent + Tracer 隔离
│   ├── downstream_client.py # 下游 mock/real 双模式客户端
│   └── observability/      # SQLite DAO + loguru sink + JSONL tracer
├── skills/                 # 9 个自包含 Skills（每个含 SKILL.md）
│   ├── slot_filling/       # 槽位填充引擎（决策树追问）
│   ├── solution_generation/# 四类配置模板渲染（Jinja2）
│   ├── solution_verification/ # 约束校验（mock）
│   ├── cei_config/         # CEI Spark 配置
│   ├── wifi_simulation/    # Wifi 仿真配置
│   ├── fault_config/       # 故障检测配置
│   ├── remote_loop/        # 远程闭环配置
│   ├── data_insight/       # 数据查询 + 归因分析（mock）
│   └── report_generation/  # Markdown 报告渲染
├── prompts/main_agent_system.md  # System Prompt（任务识别 + 流程状态机）
├── ui/
│   ├── app.py              # Gradio 入口（异步流式输出）
│   └── chat_renderer.py    # 思考/工具调用/回答的折叠渲染
└── tests/test_smoke.py     # 冒烟测试
```

## 三类任务流程

```
综合目标: slot_filling → solution_generation → [solution_verification] → [report_generation]
具体功能: cei_config | wifi_simulation | fault_config | remote_loop → 展示 → 确认
数据洞察: data_insight → [report_generation]
```

## 架构要点

1. **Skills 自包含**：模板、脚本、参考配置全在 Skill 目录内，通过 `LocalSkills` 自动扫描
2. **会话隔离**：`SessionManager` 为每个 Gradio session_hash 创建独立 Agent + Tracer
3. **模板驱动**：`solution_generation` 使用 Jinja2 按用户画像渲染四类配置，禁止凭空编造参数
4. **可观测性双写**：SQLite（结构化查询）+ JSONL（日志归档），写入失败不影响主流程
5. **下游 mock/real 切换**：`downstream.yaml` 的 `mode` 字段控制，mock 模式随机返回预设响应
6. **prompt tracer**：monkey-patch `ainvoke_stream` 记录完整 LLM 输入，不侵入 Agno 内部

## Skills 设计规范

### Google ADK 5 Agent Skills Design Patterns

所有 Skill 必须明确对应以下 5 种范式之一（参考：[ADK Skill Design Patterns](https://lavinigam.com/posts/adk-skill-design-patterns/)）：

| 范式 | 说明 | 本项目对应 Skill |
|---|---|---|
| **Tool Wrapper** | 封装已有 API/库，注入最佳实践 | `data_insight`（封装 mock 查询 API） |
| **Generator** | 从模板生成结构化输出 | `solution_generation`、`report_generation`、`cei_config`、`wifi_simulation`、`fault_config`、`remote_loop` |
| **Reviewer** | 按清单评估内容并评分 | `solution_verification`（约束校验） |
| **Inversion** | 先访谈再执行（Agent 主导提问） | `slot_filling`（槽位决策树） |
| **Pipeline** | 强制多步骤顺序执行，含质量门控 | 整体三类任务流程 |

### Skill 目录规范（Agno `LocalSkills` 约定）

```
skill_name/
├── SKILL.md          # 必须：YAML frontmatter（name/description）+ Markdown 指令
├── scripts/          # 可选：Python 脚本（agno 可发现并执行）
└── references/       # 可选：参考文件（配置示例、Jinja2 模板、Schema）
```

**关键约束**：
- `templates/` 目录名**不被** agno 的 `LocalSkills` 扫描 → 统一使用 `references/`
- `scripts/` 中的文件名通过 `get_skill_instructions` 的 `available_scripts` 字段暴露给 LLM
- `references/` 中的文件名通过 `available_references` 字段暴露给 LLM
- Skill 顶层目录中的散落文件（如裸放的 `.yaml`）对 LLM 不可见 → 必须放入 `references/`

### SKILL.md 编写规范

```markdown
---
name: skill_name
description: "一句话描述，用于 L1 元数据（~100 token，始终加载）"
---

## Metadata
- **paradigm**: 对应的 ADK 范式名称
- **when_to_use**: 触发条件

## When to Use
- ✅ 适用场景
- ❌ 不适用场景

## How to Use
（具体调用步骤，L2 按需加载）

## Scripts / References
（列出 scripts/ 和 references/ 中的文件及用途）
```

### 渐进式披露原则（Progressive Disclosure）

- **L1（~100 token）**：SKILL.md frontmatter（`name` + `description`），Agent 启动时全量加载
- **L2（完整指令）**：SKILL.md 正文，仅在 Agent 决定使用该 Skill 时通过 `get_skill_instructions` 加载
- **L3（资源文件）**：`references/` 内容，仅在脚本需要时通过 `get_skill_reference` 按需加载

**结论**：系统提示（`prompts/main_agent_system.md`）只放**协议级通用规则**（如调用顺序、输出格式），技能细节必须留在各自的 SKILL.md，不得将技能专属规则写入系统提示。

## Python 代码规范

- **类型注解**：所有函数必须有完整类型注解（参数 + 返回值），使用内置泛型（`list[str]`、`Dict[str, Any]`）
- **Docstring**：公开函数和类必须有 docstring，私有函数视复杂度决定
- **私有符号**：模块内部函数/变量以 `_` 开头（如 `_MOCK_DATA`、`_load_config`）
- **常量**：模块级常量全大写，放在 import 之后、函数之前
- **异常处理**：core 层 try/except 包裹所有 DB 和 IO 操作，失败写日志不抛异常
- **格式化**：`ruff format .`；**Lint**：`ruff check --fix .`

## Git 提交规范

类型：`feat` | `fix` | `refactor` | `docs` | `skill`（SKILL.md/scripts/references）| `test` | `config`

- 禁止 `--force` 推送到 main/master
- 使用 git push -u origin <branch> 通过 PAT URL 直接推送
- 严禁使用 GitHub MCP Server 工具（mcp__github__push_files 等）提交或推送代码，速度极慢且不可靠
- 新增/删除模块、架构或目录结构变更时必须同步更新 README.md

## 开发命令

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your-key"
python ui/app.py                          # 启动 Gradio UI (localhost:7860)
pytest tests/test_smoke.py -v             # 冒烟测试
```

## 配置说明

- `model.yaml`：支持 openai / openai_like / openrouter，`role_map` 适配非标准 API
- `slot_schema.yaml`：定义槽位依赖树，`branches` 实现条件分支选项
- `agent.yaml`：`enabled_skills` 控制加载哪些 Skill，`memory.max_turns` 控制上下文长度

## 禁止事项

**Agent 行为**：
- 不要绕过 Skill 模板直接编造配置参数
- 不要跳过 `get_skill_instructions` 直接猜测脚本文件名
- 不要将 Skill 专属规则写入 `prompts/main_agent_system.md`（违反 Progressive Disclosure 原则）

**Skill 开发**：
- 不要在 `skill_name/` 顶层放散落的资源文件（如裸放的 `.yaml`/`.json`）→ 必须放入 `references/`
- 不要创建 `templates/` 子目录（agno 不扫描）→ 统一用 `references/`
- 不要在 Skill 脚本中感知 `session_id`，持久化由 core 层处理
- Skill 新增时必须在 SKILL.md frontmatter 中标注 `paradigm`（对应 ADK 5 范式之一）

**Core 层**：
- observability 写入失败必须静默，禁止抛异常阻断主流程
- 新增/删除模块、架构或目录结构变更时必须同步更新 README.md（已有规定）
