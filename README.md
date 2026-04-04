# 家宽体验感知优化 Agent

家庭宽带用户体验感知优化智能体。基于 [Agno](https://github.com/agno-agi/agno) 框架，通过 Skills 驱动的自主循环实现从用户意图到设备配置的端到端生成。

## 核心设计

**运行时 Skill 发现 → 渐进式加载 → Agent 自主决策链路**

Agent 自主选择调用哪个 Skill，不做硬编排 Pipeline。Skills 在启动时自动扫描注册，每个 Skill 通过 SKILL.md 描述自身能力，Agent 按需加载。

```
用户输入
  │
  ▼
Agent (Agno) ── <skills_system> 动态列出所有可用 Skill
  │
  ├─ get_skill_instructions(skill_name)  → 加载使用指南
  ├─ get_skill_reference(skill_name, path) → 读取规则/模板
  └─ get_skill_script(skill_name, script, execute=True, args=[...]) → 执行脚本
         │
         └→ stdout JSON  →  Agent 解析结果，决定下一步
```

## 技术栈

| 组件 | 技术 |
|------|------|
| Agent 框架 | [Agno](https://github.com/agno-agi/agno) ≥ 2.5.14 |
| LLM 接入 | `OpenAIChat`（兼容 OpenAI API 格式，可对接内网模型） |
| Skills | `LocalSkills` 自动扫描，元工具原生执行脚本 |
| 领域知识 RAG | LanceDB 向量存储，`Knowledge.insert()` 幂等灌入 |
| 会话持久化 | `SqliteDb`（Agent + AgentOS 双层） |
| 安全护栏 | `PromptInjectionGuardrail` 输入校验 |
| Web 服务 | `AgentOS`（替代手写 FastAPI），原生 trace + API |
| 调试界面 | Gradio `ChatInterface`，挂载于 `/gradio` |
| 配置 | 纯 YAML，`load_config()` 统一加载，零硬编码 |

## 项目结构

```
broadband-agent/
├── configs/
│   ├── llm.yaml              # 模型配置（api_key / base_url / model）
│   ├── pipeline.yaml         # 运行参数 + 存储路径
│   └── logging.yaml          # 日志配置
├── app/
│   ├── main.py               # AgentOS 入口 + Gradio 挂载
│   ├── config.py             # YAML 配置加载（Pydantic）
│   ├── agent/
│   │   └── agent.py          # Agent 定义：discover_skills / build_knowledge / build_agent
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
│   └── chat_ui.py            # Gradio 调试界面
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
├── data/                     # 运行时数据（.gitignore 排除）
│   ├── agent.db              # SQLite 会话存储
│   └── lancedb/              # LanceDB 向量存储
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

```bash
uvicorn app.main:app --reload --port 8000
```

| 端点 | 说明 |
|------|------|
| http://localhost:8000/ | AgentOS API 信息（JSON） |
| http://localhost:8000/docs | Swagger API 文档 |
| http://localhost:8000/gradio | Gradio 对话调试界面 |

### 4. 运行测试

```bash
pytest tests/ -v          # 47 个测试全部通过
ruff check --fix . && ruff format .
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

### 注册机制

`discover_skills()` 在启动时扫描 `skills/` 下所有含 `SKILL.md` 的子目录，每个目录注册为一个 `LocalSkills` 实例。`Skills` 自动向 Agent 注入三个元工具：

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

## Agent 决策流程

```
阶段1 意图理解
  intent_parser/extract.py {"user_type": ..., "guarantee_period": ...}
  → complete=false → 追问（最多3轮）→ complete=true

阶段2 用户画像
  user_profiler/query_profile.py
  → missing_fields: 能推断的补全，关键字段追问，非关键字段用默认值

阶段3 方案填充
  plan_generator/generate.py
  → 5个方案模板并行填充，展示 changes 摘要

阶段4 约束校验（强制，不可跳过）
  constraint_checker/validate.py
  → passed=true → 进入转译
  → conflicts(error) → 自动修正，重新校验（最多3次）
  → warnings → 告知用户，等待确认

阶段5 配置转译
  config_translator/translate.py
  → 输出 perception/closure/optimization/diagnosis 四类配置
  → 展示摘要 + 回退方案
```

## 阶段产出物持久化

每个阶段脚本执行完毕后，`OutputSink`（`app/outputs/sink.py`）通过 Agno `tool_hooks` 机制自动将结果写入：

```
outputs/{session_id}/{stage}.json
```

**机制**：hook 纯观测，`run_context.session_id` 由框架注入，Skills 脚本零感知。

**下游对接**：数据仿真系统读取 `outputs/{session_id}/configs.json` 获取设备配置，执行完成后交由报告 Agent 生成智能报告。

| 文件 | 来源脚本 | 内容 |
|------|---------|------|
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
```

### `configs/pipeline.yaml`
```yaml
pipeline:
  max_turns: 15               # 最大工具调用次数（tool_call_limit）
  num_history_runs: 10        # 注入上下文的历史轮数
  skills_dir: "skills"        # Skills 根目录
  debug_mode: false           # 开启后打印 Agno 内部 trace
  reasoning: false            # 开启推理模型扩展思考
  clarification_max_rounds: 3 # 最大追问轮数
  max_retry_on_constraint_fail: 3

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
4. Agent 下次启动时自动发现，无需修改任何配置

### 启用跨会话用户记忆（P1）

在 `app/agent/agent.py` 中取消注释：
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
