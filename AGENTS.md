# 家宽网络调优智能助手

## 项目概述
基于多智能体架构的家宽网络调优系统，包含 1 个 Orchestrator + 5 个 SubAgent + 16 个业务 Skills。

## 环境准备
- Python 3.11+，使用 uv 管理依赖
- 所有 skill 脚本在 `skills/*/scripts/` 目录，通过 bash 调用
- 下游接口 mock/real 切换见 `configs/downstream.yaml`

## 🔴 Python 执行规则（必须遵守）
**所有 Python 脚本必须通过 `uv run python` 执行，禁止使用裸 `python` 命令。**
这是因为项目依赖（含 vendor/ce_insight_core）通过 uv 虚拟环境管理，裸 `python` 找不到这些包会直接报错。

正确示例：`uv run python skills/goal_parsing/scripts/slot_engine.py "<args>"`
错误示例：`python skills/goal_parsing/scripts/slot_engine.py "<args>"`

## 🔴 Bash Tool 路径规则（Windows 环境必须遵守）
1. **永远使用相对路径**，从项目根目录出发，禁止使用绝对路径：
   - ✅ `uv run python skills/insight_query/scripts/run_insight.py '<json>'`
   - ❌ `uv run python D:\CodeWork\broadband-agent\skills\insight_query\scripts\run_insight.py '<json>'`
2. **路径分隔符永远用 `/`**，禁止使用 `\`：
   - ✅ `skills/insight_decompose/scripts/list_schema.py`
   - ❌ `skills\insight_decompose\scripts\list_schema.py`
3. **JSON 参数用单引号包裹外层**，内部正常双引号，禁止用 `\"` 转义：
   - ✅ `uv run python skills/xxx.py '{"table": "day"}'`
   - ❌ `uv run python skills/xxx.py "{\"table\": \"day\"}"`

## Skill 脚本调用规范
- 脚本参数为 JSON 字符串，通过命令行参数传入
- 脚本输出为 JSON 到 stdout，作为最终结果
- Generator 范式脚本的 stdout **禁止二次改写**，须原样输出
- 调用形式：`uv run python skills/<skill_name>/scripts/<script>.py <args...>`

## Agent 协作规则
- 决策型 Agent (Planning / Insight) 产出方案或报告，**不执行**配置下发
- 执行型 Agent (Provisioning ×3) 接收任务载荷后按 Skill schema 提参并调用，**不做业务规则判断**
- Orchestrator 负责路由和结果汇总，不直接调用 Skill 脚本

## 目录说明
- `skills/` — 16 个自包含 Skill，每个含 SKILL.md + scripts/ + references/
- `prompts/` — 4 份 Agent 作业手册 (source of truth)
- `configs/` — 模型/团队/下游接口配置
- `vendor/` — ce_insight_core 等内部依赖
