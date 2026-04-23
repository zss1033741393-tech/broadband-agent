# 家宽网络调优智能助手

## 项目概述
基于多智能体架构的家宽网络调优系统，包含 1 个 Orchestrator + 5 个 SubAgent + 16 个业务 Skills。

## 环境准备
- Python 3.11+，使用 uv 管理依赖
- 所有 skill 脚本在 `skills/*/scripts/` 目录，通过 bash 调用
- 下游接口 mock/real 切换见 `configs/downstream.yaml`

## 🔴 Skill 脚本执行规范 （必须遵守） 

**所有 skill 脚本必须通过 `get_skill_script` 工具执行，禁止使用 bash tool 调用 Python 脚本。**
`get_skill_script` 工具参数与 agno 完全一致：
- `skill_name`：skill 目录名，如 `"insight_query"`
- `script_path`：脚本文件名，如 `"run_insight.py"`
- `execute`：设为 `true` 执行脚本，`false` 读取脚本内容
- `args`：字符串数组，传给脚本的命令行参数，如 `['{"table":"day"}']`
- `timeout`：超时秒数，默认 60

### 正确示例
get_skill_script(skill_name="insight_query", script_path="run_insight.py", execute=true, args=['{"insight_type":"OutstandingMin",...}'])
get_skill_script(skill_name="goal_parsing", script_path="slot_engine.py", execute=true, args=["<user_input>", "<state_json>"])

### 禁止的方式
❌ bash tool：uv run python skills/insight_query/scripts/run_insight.py '{"insight_type":...}'
❌ 绝对路径：D:\CodeWork\broadband-agent\skills...
❌ 裸 python：python skills/...

### 何时可以用 bash tool
- 非 Python 脚本的命令（如 git、ls、cat 等）
- 环境检查命令（如 uv sync、pip list）

## Agent 协作规则
- 决策型 Agent (Planning / Insight) 产出方案或报告，**不执行**配置下发
- 执行型 Agent (Provisioning ×3) 接收任务载荷后按 Skill schema 提参并调用，**不做业务规则判断**
- Orchestrator 负责路由和结果汇总，不直接调用 Skill 脚本

## 目录说明
- `skills/` — 16 个自包含 Skill，每个含 SKILL.md + scripts/ + references/
- `prompts/` — 4 份 Agent 作业手册 (source of truth)
- `configs/` — 模型/团队/下游接口配置
- `vendor/` — ce_insight_core 等内部依赖
