# 家宽网络调优智能助手

基于 [agno](https://github.com/agno-agi/agno) 框架构建的家宽网络调优场景单体智能体原型。

## 功能特性

支持三类任务入口：

1. **综合性目标设定** — 用户描述业务目标，系统自动拆解→生成方案→校验→下发→报告
2. **具体功能调用** — CEI 配置 / Wifi 仿真 / 故障配置 / 远程闭环
3. **数据洞察分析** — 网络质量数据查询与归因分析

## 技术栈

- Python 3.11 + agno >= 2.5.14
- Gradio (Web UI)
- loguru (应用日志) + SQLite (持久化与业务追踪)
- Jinja2 (配置模板渲染)

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 设置 API Key
export OPENAI_API_KEY="your-api-key"

# 启动应用
python ui/app.py
```

访问 http://localhost:7860 开始使用。

## 项目结构

```
├── configs/          # YAML 配置文件
├── skills/           # agno 原生 Skills (9 个)
├── prompts/          # System Prompt
├── core/             # 核心模块 (会话管理、模型加载、下游客户端、可观测性)
├── ui/               # Gradio Web UI
├── data/             # 运行时数据 (SQLite、日志)
└── tests/            # 冒烟测试
```

## 配置

- `configs/model.yaml` — 模型 provider/endpoint 配置
- `configs/agent.yaml` — Agent 配置
- `configs/downstream.yaml` — 下游系统接口（mock/real 切换）
- `skills/slot_filling/slot_schema.yaml` — 综合目标槽位定义（slot_filling Skill 内置）

## 测试

```bash
pip install pytest
pytest tests/ -v
```
