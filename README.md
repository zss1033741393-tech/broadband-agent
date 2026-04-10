# Broadband Agent Demo

家宽网络调优智能助手的 **端到端 Demo 仓库**，包含：

- **`backend/`** — 基于 [agno](https://github.com/agno-agi/agno) 框架的多智能体后端（Team + 10 个业务 Skills）
- **`frontend/`** — 基于 Vite + React + Ant Design 的暗色操作台，支持 SSE 流式对话与 Agent 结果可视化

两端可独立运行，也可联调；前端自带完整 Mock 数据，**无后端依赖也能完整演示所有功能**。

---

## 项目定位

面向网络运维工程师的 AI Agent 操作台：用户通过自然语言描述目标或故障现象，Agent 负责：

1. 追问并澄清用户意图
2. 调用网络数据、执行诊断、下发配置
3. 将步骤、思考过程、图表与 Markdown 报告以**流式**方式呈现到前端

---

## 整体架构

```
┌──────────────────────────┐    SSE 流式对话    ┌──────────────────────────┐
│   frontend/ (React)      │ ◄───────────────► │   backend/ (agno Team)   │
│                          │                    │                          │
│  - 会话列表 / 对话界面     │   REST + SSE      │  OrchestratorTeam        │
│  - 步骤卡 / 结论 / 图表    │                    │    ├─ PlanningAgent      │
│  - MSW Mock（离线演示）    │                    │    ├─ InsightAgent       │
│                          │                    │    └─ 3 × ProvisioningAgent │
└──────────────────────────┘                    └──────────────────────────┘
                                                           │
                                                           ▼
                                                   10 业务 Skills
                                                (plan_design / data_insight /
                                                 fault_diagnosis / cei_pipeline
                                                 / wifi_simulation ...)
```

前后端通过 `frontend/docs/03_API.md` 中定义的接口契约对接，核心是一条 SSE 流传输 `thinking / step_start / sub_step / text / render / done` 等事件类型。

---

## 快速开始

### 前置要求

| 工具 | 版本 |
|------|------|
| Node.js | >= 20 |
| pnpm | >= 9 |
| Python | >= 3.11 |
| pip / venv | 最新版 |

---

### 方式一：仅前端 Mock 模式（推荐首次体验）

前端自带 MSW Mock，**无需启动后端**即可完整演示所有界面与交互：

```bash
cd frontend
pnpm install
pnpm dev
```

浏览器打开 http://localhost:5173 ，即可：

- 查看 4 条 Mock 会话（含图像 / 数据洞察 / 普通对话 / 空会话）
- 发送消息体验 SSE 流式对话（步骤卡逐条出现 + 结论流式追加）
- 右侧面板展示拓扑图、4 张 ECharts 图表、Markdown 报告

> Mock 模式由 `frontend/.env.development` 中 `VITE_USE_MOCK=true` 控制。

---

### 方式二：启动后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export OPENAI_API_KEY="your-api-key"

# 启动后端服务（具体入口见 backend/README.md）
```

> 注：`backend/ui/` 目录下有基于 Gradio 的临时 UI，后续会删除，请以 `frontend/` 为准。

---

### 方式三：前后端联调

1. 按方式二启动后端，确认 API 可访问
2. 修改前端环境变量切到真实后端：

   ```bash
   # frontend/.env.development
   VITE_USE_MOCK=false
   VITE_API_BASE=http://localhost:8080/api
   ```

3. 重启前端 `pnpm dev`，即可与真实 Agent 对话

---

## 目录结构

```
broadband-agent-demo/
├── backend/                  # 多智能体后端
│   ├── configs/              # 模型 / Agent / 下游系统配置
│   ├── core/                 # Agent factory / session / observability
│   ├── prompts/              # 4 份 Agent 作业手册
│   ├── skills/               # 10 个业务 Skills
│   ├── fae_poc/              # FAE 平台对接 POC
│   ├── tests/
│   └── README.md             # 后端完整文档
│
├── frontend/                 # Web 操作台
│   ├── docs/                 # 6 份前端文档 (PRD / UI / API / Tech / Guide / Mock)
│   │   └── mock/             # 完整 Mock JSON 数据
│   ├── src/
│   │   ├── pages/Workspace/  # 三栏主界面 (NavBar / LeftPanel / RightPanel)
│   │   ├── store/            # Zustand 状态管理
│   │   ├── api/              # axios + SSE fetch 封装
│   │   ├── utils/sseParser.ts # EventSource 协议解析
│   │   ├── mocks/            # MSW handlers + SSE 回放
│   │   └── types/            # 前端类型定义
│   └── vite.config.ts
│
└── README.md                 # 本文件
```

---

## 文档索引

### 前端
- [`frontend/docs/01_PRD.md`](frontend/docs/01_PRD.md) — 产品需求
- [`frontend/docs/02_UI_SPEC.md`](frontend/docs/02_UI_SPEC.md) — 界面规格
- [`frontend/docs/03_API.md`](frontend/docs/03_API.md) — 前后端接口契约（**前后端对接的单一事实源**）
- [`frontend/docs/04_TECH.md`](frontend/docs/04_TECH.md) — 技术栈与目录约束
- [`frontend/docs/05_DEVELOPMENT_GUIDE.md`](frontend/docs/05_DEVELOPMENT_GUIDE.md) — 7 阶段开发指南
- [`frontend/docs/06_MOCK_DATA.md`](frontend/docs/06_MOCK_DATA.md) — Mock 数据说明

### 后端
- [`backend/README.md`](backend/README.md) — 架构、Skill 设计范式、快速开始
- [`backend/CLAUDE.md`](backend/CLAUDE.md) — 开发者（或 AI Agent）协作指南

---

## 技术栈

### Backend

- Python 3.11 · agno >= 2.5.14
- loguru（应用日志）· SQLite（会话持久化与业务追踪）
- Jinja2（配置模板渲染）

### Frontend

- React 18 · TypeScript 5 · Vite 5
- Ant Design 5（强制 Dark 主题）
- Zustand（状态管理）· axios（REST）· 原生 fetch + ReadableStream（SSE）
- ECharts 5（数据可视化）· react-markdown + remark-gfm（报告渲染）
- MSW 2（Mock Service Worker）

---

## Demo 亮点

- **零后端依赖演示** — MSW Mock 覆盖所有接口，包括 SSE 流式回放，`pnpm dev` 一条命令完整跑通
- **三种典型 Agent 场景** — 图像展示（拓扑图排查）/ 数据洞察（多图表 + Markdown 周报）/ 普通对话
- **完整 SSE 事件协议** — `thinking / step_start / sub_step / step_end / text / render / done / error` 八类事件，支持流式中断与错误恢复
- **前后端契约驱动** — `docs/03_API.md` 是前后端联调的单一事实源，类型定义、Mock 数据、真实接口三者对齐

---

## License

MIT — 见 [`backend/LICENSE`](backend/LICENSE)
