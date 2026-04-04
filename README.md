# 家宽 CEI 体验优化 Agent

家庭宽带 CEI（Customer Experience Index）体验感知优化智能体。基于 [Agno](https://github.com/agno-agi/agno) 框架，通过多 Agent 协作实现从用户意图到设备配置的端到端生成。

## 核心设计

**OrchestratorTeam（主控）→ 4 个专家子 Agent → Skills 按需执行**

主控（`TeamMode.coordinate`）协调 4 个专家子 Agent，每个子 Agent 只处理本阶段职责、只加载本阶段所需 Skills，context 相互隔离，消除跨阶段污染。

```
用户输入
  │
  ▼
OrchestratorTeam ──────────────────────────────────────────┐
  │ 委托给                                                   │
  ├─ IntentAgent   (intent_parser + user_profiler Skills)   │ context
  ├─ PlanAgent     (plan_generator Skill)                   │ 独立
  ├─ ConstraintAgent (constraint_checker Skill)             │
  └─ ConfigAgent   (config_translator Skill)                │
         │                                                   │
         └→ stdout JSON / 直接 Python 工具 → 产出写入 outputs/
```

## 技术栈

| 组件 | 技术 |
|------|------|
| Agent 框架 | [Agno](https://github.com/agno-agi/agno) ≥ 2.5.14 |
| 多 Agent | `Team(mode=TeamMode.coordinate)` + 4 个专家 `Agent` |
| LLM 接入 | `OpenAIChat`（兼容 OpenAI API 格式，可对接内网模型） |
| Skills | `LocalSkills` 按需加载，元工具原生执行脚本 |
| 直接工具 | `check_constraints` / `translate_configs`（无 subprocess 开销） |
| 领域知识 RAG | LanceDB 向量存储，`Knowledge.insert()` 幂等灌入 |
| 会话持久化 | `SqliteDb`（Team + AgentOS 双层） |
| 安全护栏 | `PromptInjectionGuardrail` 输入校验 |
| Web 服务 | `AgentOS(teams=[...])` 原生 trace + API |
| 调试界面 | Gradio `ChatInterface`，结构化活动日志 |
| 配置 | 纯 YAML，`load_config()` 统一加载，零硬编码 |

## 项目结构

```
broadband-agent/
├── configs/
│   ├── llm.yaml              # 模型配置（api_key / base_url / model）
│   ├── pipeline.yaml         # 运行参数 + 存储路径
│   └── logging.yaml          # 日志配置
├── app/
│   ├── main.py               # AgentOS 入口（AgentOS(teams=[get_team()])）
│   ├── config.py             # YAML 配置加载（Pydantic）
│   ├── agent/
│   │   ├── tools.py          # 共享工具：get_pipeline_file / check_constraints / translate_configs
│   │   ├── intent_agent.py   # IntentAgent（目标解析 + 追问 + 用户画像）
│   │   ├── plan_agent.py     # PlanAgent（五大方案生成）
│   │   ├── constraint_agent.py # ConstraintAgent（约束校验，可选）
│   │   ├── config_agent.py   # ConfigAgent（4 类配置生成）
│   │   ├── team.py           # OrchestratorTeam 定义，get_team() 入口
│   │   └── agent.py          # 向后兼容包装，get_agent() → get_team()
│   └── outputs/
│       └── sink.py           # OutputSink：tool_hook 拦截脚本结果，按 session 写文件
├── skills/                   # 自包含 Skills（自动扫描）
│   ├── intent_parser/        # 意图解析与追问
│   ├── user_profiler/        # 用户画像补全
│   ├── plan_generator/       # 五大方案模板填充
│   ├── constraint_checker/   # 约束校验（强制步骤）
│   ├── config_translator/    # NL2JSON 配置转译
│   └── domain_expert/        # 领域知识（Knowledge RAG）
├── ui/
│   └── chat_ui.py            # Gradio 调试界面（结构化活动日志）
├── data/                     # 运行时数据（.gitignore 排除）
│   ├── agent.db              # SQLite 会话存储
│   └── lancedb/              # LanceDB 向量存储
├── outputs/                  # 阶段产出物（运行时，.gitignore 排除）
│   └── {session_id}/
│       ├── intent.json       # 意图解析结果
│       ├── profile.json      # 用户画像
│       ├── plans.json        # 五大方案
│       ├── constraint.json   # 约束校验结果
│       └── configs.json      # 设备配置（下游系统消费此文件）
├── tests/
│   ├── test_agent/           # Agent 初始化 + 流式事件 + Skills 发现测试
│   ├── test_skills/          # 各 Skill 脚本逻辑测试
│   └── test_outputs/         # OutputSink 测试
└── pyproject.toml
```

## 快速开始

### 1. 安装依赖

```bash
# 推荐：用 uv 安装（自动读取 uv.lock 精确版本）
uv sync

# 或 pip 安装
pip install -e .
```

### 2. 配置模型

编辑 `configs/llm.yaml`：

```yaml
api_key: "sk-xxx"
base_url: "https://api.openai.com/v1"  # 支持任何 OpenAI 兼容端点
model: "gpt-4o"
temperature: 0.3
max_tokens: 4096
```

### 3. 启动服务

**AgentOS 主服务**（API + 会话持久化）：
```bash
uvicorn app.main:app --reload --port 8000
```

| 端点 | 说明 |
|------|------|
| http://localhost:8000/ | AgentOS API 信息（JSON） |
| http://localhost:8000/docs | Swagger API 文档 |

**Gradio 调试界面**（独立进程，另开终端）：
```bash
python ui/chat_ui.py
```

| 端点 | 说明 |
|------|------|
| http://localhost:7860 | Gradio 对话调试界面 |

> Gradio 独立运行而非挂载到 AgentOS，原因：AgentOS 内置 TrailingSlashMiddleware 与 Gradio 路由存在重定向冲突。

### 4. 运行测试

```bash
pytest tests/ -v          # 47 个测试全部通过
ruff check --fix . && ruff format .
```

## 多 Agent 架构详解

### 子 Agent 职责与 Skills

| 子 Agent | Skills | 职责 | num_history_runs |
|----------|--------|------|-----------------|
| `IntentAgent` | intent_parser + user_profiler | 解析意图 + 追问 + 补全画像 | 4 |
| `PlanAgent` | plan_generator | 填充五大方案模板 | 2 |
| `ConstraintAgent` | constraint_checker | 校验性能/组网/冲突约束 | 2 |
| `ConfigAgent` | config_translator | 转译 4 类设备配置 | 1 |
| `OrchestratorTeam` | — | 路由委托、汇总结果、用户交互 | 4 |

### 直接 Python 工具（无 subprocess 开销）

ConstraintAgent 和 ConfigAgent 注册了直接 Python 函数工具，绕过 subprocess 调用：

| 工具 | 替代 | 说明 |
|------|------|------|
| `check_constraints(plans_file)` | `validate.py` subprocess | 直接调用规则引擎，无进程开销 |
| `translate_configs(plans_file)` | `translate.py` subprocess | 直接调用字段映射，无进程开销 |

### 决策流程

```
阶段1 目标解析+追问（IntentAgent）
  intent_parser/extract.py + user_profiler/query_profile.py
  → complete=false → 追问（最多3轮）→ complete=true
  → 产出：intent.json + profile.json

阶段2 生成方案（PlanAgent）
  plan_generator/generate.py
  → 5个方案模板并行填充，展示 changes 摘要
  → 产出：plans.json

阶段3 约束校验（ConstraintAgent，必须执行）
  check_constraints(plans_file)  ← 直接 Python 工具
  → passed=true → 进入配置生成
  → conflicts(error) → 返回 suggestions 给 OrchestratorTeam → 重新委托 PlanAgent（最多3次）
  → warnings → 告知用户，等待确认

阶段4 配置生成（ConfigAgent）
  translate_configs(plans_file)  ← 直接 Python 工具
  → 输出 perception/closure/optimization/diagnosis 四类配置
  → 展示摘要 + 回退方案
  → 产出：configs.json
```

## Skills 详解

每个 Skill 是完全自包含的能力包，新增 Skill 只需在 `skills/` 下新建目录，无需修改任何其他文件。

### Skill 目录结构

```
skills/{skill_name}/
├── SKILL.md        # frontmatter(name + description) + 使用指南 + 脚本调用格式
├── scripts/        # Python 可执行脚本（需有 if __name__ == "__main__": 入口）
└── references/     # JSON 模板、规则文档、参考资料
```

### 元工具（Skills 自动注入）

每个子 Agent 加载的 Skills 自动注入三个元工具：

| 元工具 | 用途 |
|--------|------|
| `get_skill_instructions(skill_name)` | 读取 SKILL.md 使用指南（调用脚本前必须先加载） |
| `get_skill_reference(skill_name, path)` | 读取 references/ 中的规则/模板文件 |
| `get_skill_script(skill_name, script, execute=True, args=[...])` | 执行脚本，获取 stdout JSON |

### Skill 列表

| Skill | 脚本 | 功能 |
|-------|------|------|
| `intent_parser` | `extract.py` | 解析用户自然语言意图，校验完整性，生成追问 |
| `user_profiler` | `query_profile.py` | 查询用户历史画像，补全缺失字段 |
| `plan_generator` | `generate.py` | 基于意图目标并行填充五大优化方案模板 |
| `constraint_checker` | `validate.py` | 校验方案的性能约束、组网约束、策略冲突（**强制步骤**） |
| `config_translator` | `translate.py` | 将语义方案转译为设备可下发的配置（NL2JSON） |
| `domain_expert` | 无脚本 | 领域知识参考，已灌入 LanceDB，优先使用 Knowledge 检索 |

## 阶段产出物持久化

每个阶段脚本执行完毕后，`OutputSink`（`app/outputs/sink.py`）通过 Agno `tool_hooks` 机制自动将结果写入：

```
outputs/{session_id}/{stage}.json
```

**机制**：hook 纯观测，`run_context.session_id` 由框架注入，Skills 脚本零感知。

**下游对接**：数据仿真系统读取 `outputs/{session_id}/configs.json` 获取设备配置。

| 文件 | 来源 | 内容 |
|------|------|------|
| `intent.json` | `extract.py` | 结构化意图目标 |
| `profile.json` | `query_profile.py` | 用户画像 |
| `plans.json` | `generate.py` | 五大方案填充结果 |
| `constraint.json` | `validate.py` | 约束校验结果（重试时覆盖） |
| `configs.json` | `translate.py` | 设备下发配置（下游消费） |

## 配置参数

### `configs/llm.yaml`
```yaml
api_key: "sk-xxx"
base_url: "https://api.openai.com/v1"
model: "gpt-4o"
temperature: 0.3
max_tokens: 4096
provider: "openai"    # openai（含兼容接口）| anthropic
reasoning: false      # 仅原生推理模型（deepseek-reasoner / o1/o3）开启
```

### `configs/pipeline.yaml`
```yaml
pipeline:
  max_turns: 15                  # 最大工具调用次数（tool_call_limit）
  num_history_runs: 4            # 注入上下文的历史轮数（主控 Team 级）
  skills_dir: "skills"           # Skills 根目录
  debug_mode: false              # 开启后打印 Agno 内部 trace
  clarification_max_rounds: 3    # 最大追问轮数
  max_retry_on_constraint_fail: 3
  use_llm_constraint: false      # 切换约束校验为 LLM 实现（预留）
  use_llm_translation: false     # 切换配置转译为 LLM 实现（预留）
  agents:                        # 各子 Agent 独立配置
    intent:
      num_history_runs: 4
      model: ~                   # null = 继承 llm.yaml 的模型，可单独指定
    plan:
      num_history_runs: 2
      model: ~
    constraint:
      num_history_runs: 2
      model: ~
    config:
      num_history_runs: 1
      model: ~

storage:
  sqlite_db_path: "data/agent.db"
  sqlite_table: "agent_sessions"
  lancedb_uri: "data/lancedb"
  lancedb_table: "domain_knowledge"
```

## 扩展指南

### 新增 Skill

1. 在 `skills/` 下创建新目录，如 `skills/my_skill/`
2. 创建 `SKILL.md`（必须包含 `name` 和 `description` frontmatter）
3. 在 `scripts/` 下创建脚本，脚本必须：
   - 接受 CLI 参数（`sys.argv[1:]`）
   - 输出 JSON 到 stdout
   - 包含 `if __name__ == "__main__":` 入口
4. 在对应子 Agent 的 `Skills(loaders=[...])` 中注册该 Skill

### 新增子 Agent

1. 在 `app/agent/` 下创建 `my_agent.py`，参照 `intent_agent.py` 结构
2. 在 `app/agent/team.py` 的 `build_team()` 中将新 Agent 加入 `members=[]`

### 启用跨会话用户记忆（P1）

在 `app/agent/team.py` 的 `build_team()` 中：
```python
# enable_user_memories=True,
```

## 开发规范

```
feat: 新功能
fix:  修复
refactor: 重构
skill: Skills 变更（SKILL.md / scripts / references）
```

**注意**：
- `data/` 目录（SQLite + LanceDB）已加入 `.gitignore`，不提交运行时数据
- `design.md` 仅本地维护，禁止提交
- 所有配置从 YAML 加载，零硬编码
