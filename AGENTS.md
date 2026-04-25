# 家宽网络调优智能助手

## 环境
- Python 3.11+，`uv sync` 安装全部依赖

## 目录结构

| 路径 | 用途 |
|---|---|
| `skills/` | 自包含 Skill，每个含 SKILL.md + scripts/ + references/ |
| `prompts/` | Agent 作业手册（source of truth） |
| `configs/` | 模型 / 团队 / 下游接口配置 |
| `vendor/` | ce_insight_core 等内部依赖 |

## 通用约定

- **先读 SKILL.md 再执行脚本**：调用任何 skill 前，先用 Skill tool 加载对应 SKILL.md 获取参数 schema
- **脚本通过 `get_skill_script` 工具调用**，禁止 bash tool 直接跑 Python 脚本
- **stdout 不改写**：脚本输出禁止二次改写，原样输出
