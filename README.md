# 家宽体验感知优化 Agent

家庭宽带用户体验感知优化智能体原型。通过 Agno 框架构建 Skills 驱动的 Agent，实现用户意图到设备配置的端到端自动化生成。

## 核心架构

**Agent 自主决策 + Skills 渐进式加载**

Agent 根据用户输入和上下文自主选择调用哪个 Skill，system prompt 只提供流程指导，不做硬编排。

```
用户输入 → Agent 理解意图 → 自主选择 Skill → 执行 → 判断下一步
                                 ↑                        │
                                 └────────────────────────┘
```

## 技术栈

- Python 3.11+
- [Agno](https://github.com/agno-agi/agno) — Agent 框架，原生 Skills 支持
- FastAPI — 后端服务
- Gradio — 对话调试界面
- SQLite — 会话/配置持久化
- OpenAI API 兼容格式 — 可对接内部开源模型

## 项目结构

```
broadband-agent/
├── configs/                    # YAML 配置（含 API Key，不拆 .env）
│   ├── llm.yaml                # 模型注册
│   ├── pipeline.yaml           # 运行参数
│   └── logging.yaml            # 日志配置
├── app/                        # FastAPI 后端
│   ├── main.py                 # 入口 + Gradio 挂载
│   ├── config.py               # 配置加载
│   ├── agent/                  # Agent 核心
│   │   ├── agent.py            # Agno Agent 定义 + system prompt
│   │   ├── skill_loader.py     # Skills 发现与注册
│   │   └── tracer.py           # Agent 轨迹记录
│   ├── models/                 # Pydantic 数据模型
│   ├── db/                     # SQLite
│   ├── logger/                 # 日志模块
│   └── api/                    # FastAPI 路由
├── skills/                     # 自包含 Skills（核心）
│   ├── intent_parsing/         # 意图解析与追问
│   ├── user_profile/           # 用户画像补全
│   ├── plan_filling/           # 五大方案模板填充
│   ├── constraint_check/       # 约束校验
│   ├── config_translation/     # NL2JSON 配置转译
│   └── domain_knowledge/       # 领域知识（仅参考资料）
├── ui/
│   └── chat_ui.py              # Gradio 三栏调试界面
├── traces/                     # Agent 轨迹（按 session_id 隔离）
├── tests/
├── design.md                   # 详细设计文档
└── pyproject.toml
```

## 快速开始

### 1. 安装依赖

```bash
pip install agno fastapi uvicorn gradio pydantic openai pyyaml aiosqlite
```

### 2. 配置模型

编辑 `configs/llm.yaml`，填入你的 API Key 和 base_url：

```yaml
models:
  main:
    api_key: "sk-xxx"
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o"
```

### 3. 启动服务

```bash
uvicorn app.main:app --reload --port 8000
```

- API 文档：http://localhost:8000/docs
- Gradio 界面：http://localhost:8000/ui

### 4. 运行测试

```bash
pip install pytest
pytest tests/ -v
```

## Skills 说明

每个 Skill 是自包含的能力包，结构如下：

```
skills/{skill_name}/
├── SKILL.md          # frontmatter(name + description) + 何时使用 + 处理步骤 + 规则
├── scripts/          # Python 执行脚本
└── references/       # JSON 模板、规则文档、示例
```

新增 Skill 只需在 `skills/` 下新建目录 + `SKILL.md`，无需修改任何其他文件。

| Skill | 功能 |
|-------|------|
| `intent_parsing` | 解析用户自然语言，生成结构化意图目标，信息不全时追问 |
| `user_profile` | 从历史数据和 KPI 补全用户画像 |
| `plan_filling` | 基于意图目标并行填充五大方案模板 |
| `constraint_check` | 校验方案的性能约束、组网约束和策略冲突 |
| `config_translation` | 将语义化方案转译为设备可下发的配置（NL2JSON） |
| `domain_knowledge` | 家宽领域知识参考（CEI 指标、设备能力、术语表） |

## API

```
POST /api/chat                        # 发送对话消息
GET  /api/skills                      # 列出所有可用 Skills
GET  /api/sessions/{session_id}/trace # 获取会话轨迹
GET  /api/health                      # 健康检查
```

## 设计文档

详见 [design.md](design.md)。
