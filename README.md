# 家宽体验感知优化 Agent 智能体

家庭宽带用户体验优化的 Agent Pipeline 原型。用户输入意图 → 解析追问 → 基于 JSON 模板填充方案 → 约束校验 → NL2JSON 配置输出。

---

## 快速启动

### 1. 安装依赖

```bash
pip install -e .
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 LLM API Key：

```bash
LLM_API_KEY=sk-xxx                 # LLM API Key
SQLITE_DB_PATH=./data/agent.db     # 数据库路径（默认即可）
LOG_LEVEL=DEBUG                    # 日志级别
```

### 3. 启动服务

```bash
uvicorn app.main:app --reload
```

服务启动后：
- **API 文档**：http://localhost:8000/docs
- **Gradio 调试界面**：http://localhost:8000/ui

### 4. 单独运行 Gradio 界面（开发调试）

```bash
python ui/chat_ui.py
```

访问 http://localhost:7860

---

## 项目结构

```
broadband-agent/
├── app/                         # FastAPI 后端
│   ├── main.py                  # 应用入口，挂载 Gradio UI
│   ├── config.py                # 多模型 LLM 配置加载（按 Stage fallback）
│   │
│   ├── agents/                  # Agent 定义
│   │   ├── pipeline.py          # Pipeline 编排（Stage1→2→3→4）
│   │   ├── intent_agent.py      # Stage1：意图解析 + 追问
│   │   ├── plan_agent.py        # Stage2：方案生成（模板填充）
│   │   ├── constraint_agent.py  # Stage3：约束校验 + 回退
│   │   └── config_agent.py      # Stage4：NL2JSON 配置转译
│   │
│   ├── tools/                   # Tool 函数（Agent 可调用）
│   │   ├── profile_tools.py     # 用户画像读写
│   │   ├── template_tools.py    # 模板加载与填充
│   │   ├── constraint_tools.py  # 约束规则校验
│   │   └── config_tools.py      # 配置转译与导出
│   │
│   ├── models/                  # Pydantic 数据模型
│   │   ├── intent.py            # IntentGoal（Stage1 输出）
│   │   ├── plan.py              # FilledPlan / ConstraintCheckResult
│   │   └── config.py            # PipelineOutput（4 类配置）
│   │
│   ├── db/                      # SQLite 存储
│   │   ├── database.py          # 连接管理 + 建表
│   │   └── crud.py              # 异步 CRUD 操作
│   │
│   ├── logger/                  # 结构化日志
│   │   └── logger.py            # get_logger / log_step / log_llm_call
│   │
│   └── api/
│       └── routes.py            # FastAPI 路由（/api/v1/chat 等）
│
├── skills/                      # Skills Markdown 文件（渐进式加载）
│   ├── stage1/
│   │   ├── intent_parsing_skill.md   # 意图解析规则、追问策略
│   │   └── user_profile_skill.md     # 用户画像补全逻辑
│   ├── stage2/
│   │   ├── plan_filling_skill.md     # 模板参数决策规则
│   │   └── domain_knowledge_skill.md # 家宽领域知识
│   ├── stage3/
│   │   └── constraint_check_skill.md # 约束规则、冲突检测
│   └── stage4/
│       └── config_translation_skill.md # NL2JSON 转译规范
│
├── templates/                   # JSON 方案基线模板（勿随意修改结构）
│   ├── user_profile.json
│   ├── cei_perception_plan.json
│   ├── fault_diagnosis_plan.json
│   ├── remote_closure_plan.json
│   ├── dynamic_optimization_plan.json
│   └── manual_fallback_plan.json
│
├── configs/                     # YAML 配置（非敏感信息）
│   ├── llm.yaml                 # 多模型配置，按 Stage 独立指定
│   ├── pipeline.yaml            # Pipeline 运行参数
│   └── logging.yaml             # 日志分层配置
│
├── ui/
│   └── chat_ui.py               # Gradio 对话调试界面
│
├── tests/
│   ├── test_agents/             # Agent 测试（含集成测试）
│   ├── test_tools/              # Tool 函数单元测试
│   └── test_templates/          # JSON 模板完整性测试
│
├── outputs/configs/             # 运行时生成的配置文件（按 session_id 分目录）
├── logs/                        # 运行时日志（app.log / pipeline.log）
├── data/                        # SQLite 数据库文件
├── pyproject.toml
└── .env.example
```

---

## Pipeline 架构

```
用户输入
   │
   ▼
[Stage 1] IntentParser — 意图解析 + 追问
   │  Skills: intent_parsing_skill + user_profile_skill
   │  输出: IntentGoal JSON
   │
   ▼
[Stage 2] PlanFiller — 方案生成（模板填充）
   │  Skills: plan_filling_skill + domain_knowledge_skill
   │  基于 5 个 JSON 模板，调整参数值
   │  输出: 5 个填充后方案
   │
   ▼
[Stage 3] ConstraintChecker — 约束校验
   │  Skills: constraint_check_skill
   │  校验不通过 → 回退 Stage2（最多 3 次）
   │
   ▼
[Stage 4] ConfigTranslator — NL2JSON 配置输出
      Skills: config_translation_skill
      输出: 4 类设备配置 JSON 文件
```

---

## 常用命令

```bash
# 启动开发服务器
uvicorn app.main:app --reload

# 运行所有单元测试（不含需要 LLM 的集成测试）
pytest tests/ -m "not integration"

# 运行集成测试（需配置 LLM_API_KEY）
pytest tests/ -m integration -v

# 运行单个测试文件
pytest tests/test_agents/test_intent_agent.py -v

# 代码检查
ruff check .

# 代码格式化
ruff format .
```

---

## 配置说明

### LLM 模型配置（`configs/llm.yaml`）

不同 Stage 可使用不同模型，未单独配置的 Stage 自动 fallback 到 `default`：

| Stage | 默认模型 | 说明 |
|-------|---------|------|
| Stage1 意图解析 | gpt-4o | 语义理解强，追问自然 |
| Stage2 方案生成 | gpt-4o-mini | 模板填充，轻量模型即可 |
| Stage3 约束校验 | gpt-4o-mini | 规则判断，低成本 |
| Stage4 配置转译 | gpt-4o | NL2JSON 结构化输出精度要求高 |

修改 `configs/llm.yaml` 中的 `base_url` 可对接内部部署的开源模型（Qwen/GLM 等）。

### Pipeline 参数（`configs/pipeline.yaml`）

```yaml
pipeline:
  max_retry_on_constraint_fail: 3   # 约束校验失败最大重试次数
  stage2_parallel: false            # true=并行填充5个方案（快），false=串行（调试用）
  enable_stage3: true               # 可关闭约束校验（调试时）
  enable_stage4: true               # 可关闭配置转译（调试时）
```

---

## API 接口

### POST `/api/v1/chat` — 主对话接口

```json
// 请求
{
  "user_input": "我家里有直播需求，晚上 8 点到 11 点经常卡顿",
  "user_id": "user_001",
  "session_id": null
}

// 响应（status=waiting_followup 时需继续追问）
{
  "session_id": "abc-123",
  "status": "done",
  "output_files": ["outputs/configs/abc-123/perception_config.json", "..."],
  "intent_summary": {"user_type": "直播用户", "priority_level": "high"}
}
```

### GET `/api/v1/output/{session_id}` — 获取生成的配置

### GET `/api/v1/health` — 健康检查

---

## 领域术语

| 术语 | 说明 |
|------|------|
| CEI | Customer Experience Index，用户体验指数 |
| NCE | Network Cloud Engine，网络云引擎 |
| NL2JSON | Natural Language to JSON，自然语言转配置 |
| 感知粒度 | 体验指标的采集精度（采样间隔、聚合窗口等） |
| 闭环 | 从发现问题到解决问题的完整处置流程 |
| 稽核 | 闭环操作后的效果审计和回滚机制 |
| APPflow | 应用流量识别和管控策略 |
