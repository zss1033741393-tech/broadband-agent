# 家宽体验感知优化 Agent 智能体 — 原型设计文档

> **版本**: v0.2  
> **日期**: 2026-04-03  
> **作者**: [待填]  
> **状态**: 待 Review

---

## 1. 项目概述

### 1.1 背景

家庭宽带用户体验优化涉及多个环节：体验感知预警、故障诊断、远程闭环处置、智能动态优化、人工兜底保障。当前这些环节依赖人工配置，参数调整繁琐且缺乏智能化联动。

本项目构建一个 **Agent 智能体原型**，通过 Skills 驱动的智能体自主决策架构，实现用户意图到设备配置的端到端自动化生成。

### 1.2 目标

- **1 周内**交付可演示的原型 demo
- 验证 Agent 自主决策 + Skills 渐进式加载的架构可行性
- Agent 根据用户输入和上下文，自主选择调用哪个 Skill、以什么顺序执行
- 后端流程优先，前端提供对话调试界面

### 1.3 范围

**原型范围内（P0）**：
- 6 个自包含 Skills（意图解析、用户画像、方案填充、约束校验、配置转译、领域知识）
- Agent 自主决策调度，system prompt 提供流程指导
- Gradio 对话调试界面
- SQLite 存储会话记录

**原型范围外（后续迭代）**：
- 底层数据指标模块对接
- 完整的用户画像自动采集
- 生产级性能优化与高可用

---

## 2. 技术选型

| 维度 | 选型 | 理由 |
|------|------|------|
| Agent 框架 | **Agno** | 原生 Skills 渐进式加载（Browse→Load→Reference→Execute）、Workflow + Knowledge 内置、Python 原生 |
| 后端 | **Python FastAPI** | 异步高性能、与 Agno 同生态 |
| 前端 | **Gradio** | 对话调试界面快速搭建 |
| LLM 接入 | **OpenAI API 兼容格式** | 统一接口，可对接内部部署的开源模型 |
| 数据存储 | **SQLite** | 轻量 demo，会话/配置记录持久化 |

### 2.1 模型配置

模型是 Agent 级别的配置，创建 Agent 时注册，运行期间不变。Skills 是纯能力包，与模型无关。

#### configs/llm.yaml

```yaml
# configs/llm.yaml

# Agent 使用的模型配置，直接注册
api_key: "sk-xxx"
base_url: "https://internal-llm.company.com/v1"
model: "gpt-4o"
temperature: 0.7
max_tokens: 4096
```

如果需要多个 Agent 实例用不同模型（比如主 Agent 用强模型，某个子任务用轻量模型），在 yaml 里注册多个：

```yaml
# configs/llm.yaml

models:
  main:
    api_key: "sk-xxx"
    base_url: "https://internal-llm.company.com/v1"
    model: "gpt-4o"
    temperature: 0.7
    max_tokens: 4096

  lightweight:
    api_key: "sk-xxx"
    base_url: "https://internal-llm.company.com/v1"
    model: "gpt-4o-mini"
    temperature: 0.3
    max_tokens: 2048
```

### 2.2 各框架 Skills 支持力度对比

| 框架 | Skills 原生支持 | 渐进式加载 | Knowledge/RAG | 适配度 |
|------|----------------|-----------|---------------|-------|
| **Agno** | ✅ 原生 Browse→Load→Reference→Execute | ✅ Lazy loading | ✅ 内置 Knowledge + RAG | ★★★★★ |
| **Pi** | ✅ Agent Skills Standard 规范 | ✅ description 自动匹配 | ❌ 无内置 RAG | ★★★（TS 生态，无 Workflow） |
| CrewAI | ⚠️ backstory+tools 模拟 | ❌ 静态全量注入 | ⚠️ 需外接 | ★★★ |
| LangGraph | ❌ 需自行管理 prompt 切换 | ⚠️ 手动实现 | ✅ LangChain 生态 | ★★★ |
| SmolAgents | ❌ 无 | ❌ | ❌ | ★ |
| OpenAI SDK | ❌ 静态 instructions | ❌ | ⚠️ 通过 tools | ★★ |

---

## 3. 系统架构

### 3.1 核心理念转变

**不是 Pipeline 编排，而是 Agent 自主决策。**

```
传统 Pipeline（❌ 旧方案）：
  Stage1 → Stage2 → Stage3 → Stage4    （固定流程，像工作流）

Agent 驱动（✅ 新方案）：
  用户输入 → Agent 理解意图 → 自主选择 Skill → 执行 → 判断下一步
                                  ↑                         |
                                  └─────────────────────────┘
  Agent 根据当前上下文决定：
    "用户说了什么？画像完整吗？该填哪个模板？有冲突吗？要转配置吗？"
```

system prompt 提供**流程指导**（建议顺序），但 Agent 可以根据实际情况跳过、回退、并行。

### 3.2 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Gradio 对话调试界面                      │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/WebSocket
┌──────────────────────▼──────────────────────────────────┐
│                   FastAPI 后端服务                         │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │                  Agno Agent                        │  │
│  │                                                    │  │
│  │  System Prompt（流程指导 + Skill 摘要列表）          │  │
│  │       │                                            │  │
│  │       ▼                                            │  │
│  │  Agent 自主决策 ──→ Browse Skill 摘要               │  │
│  │       │              │                              │  │
│  │       ▼              ▼                              │  │
│  │  Load Skill ←── 匹配最相关的 Skill                  │  │
│  │       │                                             │  │
│  │       ▼                                             │  │
│  │  Reference ──→ 读取 Skill 内的模板/参考资料          │  │
│  │       │                                             │  │
│  │       ▼                                             │  │
│  │  Execute ──→ 运行 Skill 内置脚本                    │  │
│  │       │                                             │  │
│  │       ▼                                             │  │
│  │  判断下一步 → 继续/换 Skill/追问用户/输出结果        │  │
│  └────────────────────────────────────────────────────┘  │
│                         │                                 │
│              ┌──────────▼──────────┐                     │
│              │     Skills 目录      │                     │
│              │  (自包含能力包)       │                     │
│              └─────────────────────┘                     │
│                         │                                 │
│         ┌───────────────┼───────────────┐                │
│         ▼               ▼               ▼                │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐           │
│   │SKILL.md  │   │ scripts/ │   │references│           │
│   │指导策略   │   │ 执行脚本  │   │ JSON模板  │           │
│   └──────────┘   └──────────┘   └──────────┘           │
│                                                          │
│  ┌──────────────────────┐                                │
│  │  SQLite DB            │                                │
│  │  会话记录/配置记录     │                                │
│  └──────────────────────┘                                │
└──────────────────────────────────────────────────────────┘
```

### 3.3 System Prompt 设计

system prompt **不编排流程**，只提供指导和 Skill 摘要：

```markdown
# 你是家宽体验感知优化 Agent

你是一个智能配置生成助手。用户会描述他们的保障需求，你需要理解意图、
生成优化方案、校验约束、输出设备配置。

## 工作指导（建议但不强制的顺序）

1. 先理解用户意图，如果信息不完整就追问
2. 收集到足够信息后，填充对应的方案模板
3. 填充完成后进行约束校验
4. 校验通过后转译为设备配置

你可以根据实际情况灵活调整：
- 如果用户直接给出了完整参数，可以跳过追问
- 如果某个方案不需要修改，保持默认即可
- 如果校验发现冲突，回头调整方案参数
- 如果用户中途改了需求，重新理解意图

## 可用 Skills

以下是你可以调用的能力包，根据当前任务自行选择：

{skills_summary}
```

`{skills_summary}` 由 Agno 在运行时自动注入各 Skill 的 name + description 摘要。

---

## 4. Skills 设计（核心）

### 4.1 设计原则

每个 Skill 是一个**自包含的能力包**，遵循 Agno Skills 规范：

```
skills/
└── skill_name/
    ├── SKILL.md           # 指导策略：何时用、怎么用、规则
    ├── scripts/           # 执行脚本：Python 函数/工具
    │   ├── __init__.py
    │   └── handler.py     # 核心处理逻辑
    └── references/        # 参考资源：JSON 模板、领域文档
        ├── template.json  # 该 Skill 相关的 JSON 模板
        └── examples.md    # few-shot 示例
```

**Skill 自包含意味着**：
- 模板就在 Skill 内部的 `references/` 里，不是外部 `templates/` 目录
- 处理脚本就在 Skill 内部的 `scripts/` 里，不是外部 `tools/` 目录
- Agent 加载一个 Skill 后，该 Skill 的一切资源都可直接使用

### 4.2 Skills 目录总览

```
skills/
├── intent_parsing/              # 意图解析与追问
│   ├── SKILL.md
│   ├── scripts/
│   │   └── parse_intent.py      # 解析意图、生成追问
│   └── references/
│       ├── intent_schema.json   # IntentGoal 结构定义
│       └── examples.md          # 追问对话示例
│
├── user_profile/                # 用户画像补全
│   ├── SKILL.md
│   ├── scripts/
│   │   └── profile_handler.py   # 画像查询、补全、存储
│   └── references/
│       ├── profile_template.json # 用户画像 JSON 模板
│       └── field_rules.md       # 各字段补全规则
│
├── plan_filling/                # 方案模板填充（5个子模板都在内）
│   ├── SKILL.md
│   ├── scripts/
│   │   └── filler.py            # 读取模板→决策参数→填充
│   └── references/
│       ├── cei_perception.json           # CEI 感知方案模板
│       ├── fault_diagnosis.json          # 故障诊断方案模板
│       ├── remote_closure.json           # 远程闭环方案模板
│       ├── dynamic_optimization.json     # 动态优化方案模板
│       ├── manual_fallback.json          # 人工兜底方案模板
│       └── filling_rules.md             # 参数决策规则
│
├── constraint_check/            # 约束校验
│   ├── SKILL.md
│   ├── scripts/
│   │   └── checker.py           # 性能/组网/冲突检测
│   └── references/
│       ├── performance_rules.json  # 性能约束规则
│       ├── topology_rules.json     # 组网约束规则
│       └── conflict_matrix.json    # 冲突检测矩阵
│
├── config_translation/          # NL2JSON 配置转译
│   ├── SKILL.md
│   ├── scripts/
│   │   └── translator.py       # 方案→设备配置转译
│   └── references/
│       ├── config_schema.json   # 设备配置 JSON Schema
│       └── field_mapping.md     # 语义字段→设备字段映射表
│
└── domain_knowledge/            # 家宽领域知识（被其他 Skill 引用）
    ├── SKILL.md
    └── references/
        ├── cei_metrics.md       # CEI 指标定义
        ├── device_capabilities.json  # 设备型号能力矩阵
        └── glossary.md          # 术语表
```

### 4.3 各 Skill 详细设计

#### 4.3.1 intent_parsing — 意图解析

**SKILL.md**：

```markdown
---
name: intent_parsing
description: >
  解析用户自然语言输入为结构化意图目标。识别用户类型、场景、保障时段、
  保障对象、核心指标。信息不完整时生成追问。
  当用户描述保障需求、优化需求、或任何需要理解意图的场景时使用此 Skill。
---
```

#### 4.3.2 user_profile — 用户画像

查询和补全用户画像信息。从历史数据、应用行为、网络 KPI 中提取用户先验信息。

#### 4.3.3 plan_filling — 方案模板填充

基于意图目标填充五大方案 JSON 模板。五个模板可以并行填充（asyncio.gather）。

#### 4.3.4 constraint_check — 约束校验

校验填充后的方案是否可执行。检查性能约束、组网方式约束、方案间策略冲突。

#### 4.3.5 config_translation — NL2JSON 配置转译

将语义化方案 JSON 转译为设备可执行的配置格式（NL2JSON/NL2DSL）。

#### 4.3.6 domain_knowledge — 领域知识

家宽领域专业知识。包含 CEI 指标定义、设备型号能力矩阵、术语表。仅提供参考资料，无执行脚本。

---

## 5. 项目目录结构

```
broadband-agent/
├── README.md
├── design.md                        # 本文档
├── pyproject.toml
│
├── configs/                         # 所有配置集中管理
│   ├── llm.yaml                     # 模型配置（含 API Key，按 tier 分级）
│   ├── pipeline.yaml                # 运行参数 + 存储路径
│   └── logging.yaml                 # 日志配置
│
├── app/                             # FastAPI 后端
│   ├── __init__.py
│   ├── main.py                      # FastAPI 入口 + Gradio 挂载
│   ├── config.py                    # 配置加载（YAML + .env）
│   │
│   ├── agent/                       # Agent 核心
│   │   ├── __init__.py
│   │   ├── agent.py                 # Agno Agent 定义 + system prompt
│   │   ├── skill_loader.py          # Skills 发现与注册
│   │   └── tracer.py               # Agent 轨迹记录
│   │
│   ├── models/                      # Pydantic 数据模型
│   │   ├── __init__.py
│   │   ├── intent.py
│   │   ├── plan.py
│   │   └── config.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── crud.py
│   │
│   ├── logger/
│   │   ├── __init__.py
│   │   └── logger.py
│   │
│   └── api/
│       ├── __init__.py
│       └── routes.py
│
├── skills/                          # 自包含 Skills（核心）
│   ├── intent_parsing/
│   ├── user_profile/
│   ├── plan_filling/
│   ├── constraint_check/
│   ├── config_translation/
│   └── domain_knowledge/
│
├── ui/
│   └── chat_ui.py                   # Gradio 对话调试界面
│
├── tests/
│   ├── test_skills/
│   └── test_agent/
│
├── logs/
├── traces/                          # Agent 轨迹记录（按会话保存）
└── outputs/
```

---

## 6. 开发规范

### 6.1 代码规范

- **语言**: Python 3.11+
- **类型标注**: 所有函数必须有类型标注，使用 Pydantic Model 做数据校验
- **格式化**: 使用 `ruff` 统一代码格式
- **命名**:
  - 文件名: `snake_case.py`
  - 类名: `PascalCase`
  - 函数/变量: `snake_case`
  - Skill 目录名: `snake_case`
- **Skill 规范**: 每个 SKILL.md 必须包含 frontmatter（name + description）、何时使用、处理步骤、规则

### 6.2 Git 规范

单人开发简化版：

- **分支策略**: `main`（稳定）+ `dev`（开发）
- **Commit 格式**: `<type>: <description>`
  - `feat:` 新功能
  - `fix:` 修复
  - `refactor:` 重构
  - `docs:` 文档
  - `skill:` Skills 变更（SKILL.md / scripts / references）

### 6.3 Agent Trace 轨迹记录

每次会话作为一条完整的 Agent 轨迹保存，便于调试回放和演示。

#### trace.jsonl 格式

```jsonl
{"step":1,"timestamp":"2026-04-03T14:23:01","type":"user_input","content":"我是直播用户，晚上7点到11点需要保障上行带宽"}
{"step":2,"timestamp":"2026-04-03T14:23:01","type":"agent_thinking","content":"用户提到了直播、上行带宽、时段，但没有说对卡顿的敏感度和具体应用...","skill_selected":"intent_parsing","reason":"需要解析用户意图并补全缺失信息"}
{"step":3,"timestamp":"2026-04-03T14:23:02","type":"skill_load","skill":"intent_parsing","model":"gpt-4o","tokens_in":520,"tokens_out":180,"latency_ms":1230}
{"step":4,"timestamp":"2026-04-03T14:23:03","type":"agent_output","content":"请问您对直播卡顿的敏感程度如何？主要使用什么推流应用？","missing_fields":["sensitivity","key_applications"]}
```

### 6.4 Gradio 调试界面设计

三栏布局：
- **左边**：对话区（含 Agent 思考过程折叠块）
- **右上**：阶段输出物面板（实时刷新）
- **右下**：Agent Trace 面板（精简视图 + 导出）

### 6.5 日志规范

日志标签格式 `[Skill:xxx]`：

```
[2026-04-03 14:23:01] [Skill:intent_parsing] [INFO] Agent 加载 Skill
[2026-04-03 14:23:02] [Skill:intent_parsing] [DEBUG] LLM 调用 | model=gpt-4o | tokens_in=520
[2026-04-03 14:23:15] [Skill:constraint_check] [WARN] 校验失败 | conflict="节能时段与保障时段冲突"
```

---

## 7. 开发计划

| 天数 | 里程碑 | 具体任务 |
|------|--------|---------|
| **Day 1** | 项目骨架 + Agent 核心 | 初始化项目、安装依赖、配置 LLM 连接、实现 Agno Agent + system prompt + Skill 发现机制 |
| **Day 2** | intent_parsing + user_profile Skills | 编写 SKILL.md + scripts + references、验证意图解析和追问 |
| **Day 3** | plan_filling Skill | 5 个方案模板 JSON + filling_rules.md + filler.py、验证并行填充 |
| **Day 4** | constraint_check Skill | 约束规则 + checker.py、验证校验和 Agent 自主回退 |
| **Day 5** | config_translation + domain_knowledge | NL2JSON 转译 + 领域知识、端到端流程跑通 |
| **Day 6** | Gradio 前端 + 联调 | 对话界面 + API 接入 + 端到端调试 |
| **Day 7** | 演示准备 | Bug 修复、演示场景数据、演示脚本 |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Agent 自主决策不稳定（选错 Skill / 循环调用） | 流程跑偏 | system prompt 提供清晰的流程指导 + Skill description 要精准具体 + 设置最大调用轮次 |
| 内部开源模型对 Skill 指令遵循不够 | 方案不准确 | SKILL.md 保持精简 + scripts 里硬编码核心逻辑 + few-shot 示例 |
| 并行填充时部分模板失败 | 方案不完整 | asyncio.gather 配合 return_exceptions=True + 失败重试 |
| NL2JSON 转译准确率不够 | 配置不可用 | config_schema.json 严格校验 + 人工审核兜底 |
| 1 周时间紧张 | 功能不完整 | intent_parsing + plan_filling 必须跑通，其他 Skill 可简化 |

---

## 附录 A — 配置文件

**`configs/pipeline.yaml`**：

```yaml
pipeline:
  max_skill_rounds: 20              # Agent 最大 Skill 调用轮次（防止死循环）
  plan_filling_parallel: true        # 方案填充是否并行
  max_retry_on_constraint_fail: 3    # 约束校验失败最大回退次数

storage:
  sqlite_db_path: "./data/agent.db"
  traces_dir: "./traces"
  log_level: "DEBUG"
```

## 附录 B — 关键依赖

```toml
[project]
requires-python = ">=3.11"

[project.dependencies]
agno = ">=2.5"
fastapi = ">=0.115"
uvicorn = ">=0.30"
gradio = ">=5.0"
pydantic = ">=2.0"
openai = ">=1.50"
pyyaml = ">=6.0"
aiosqlite = ">=0.20"
ruff = ">=0.8"
```
