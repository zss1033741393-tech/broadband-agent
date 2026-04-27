# fae plugin

Hummingbird 的 free-code 插件：家宽网络调优多 Agent 系统。

由 Hummingbird `cc-bridge` 通过 `--plugin-dir` 加载到 free-code 子进程。
完整集成方案见 Hummingbird 仓库 [docs/fae-plugin-integration.md](https://github.com/zss1033741393-tech/Hummingbird/blob/fan-fae-dev/docs/fae-plugin-integration.md)。

## 目录结构

| 路径 | 用途 |
|---|---|
| `plugin.json` | free-code 插件清单（声明 `name: "fae"`，仅暴露 agents） |
| `agents/` | 6 个 Agent 定义（自包含，frontmatter + system prompt 全在 .md 中） |
| `hooks/` | session_start hook：自动 `uv sync` 准备 Python 环境 |
| `skills/` | 16 个 Python Skill 实现（Agent 通过 Bash 调用） |
| `vendor/` | 本地 editable Python 包（`ce_insight_core` / `fae_sim`） |
| `fae_poc/` | FAE 平台客户端入口（`config.ini` + `NCELogin.py` 由用户本地放置） |
| `pyproject.toml` | Python 依赖（uv 管理） |

## Agent 列表

| Agent | 类型 | 调用的 Skills |
|---|---|---|
| `fae:orchestrator` | 路由 | 通过 `Agent` 工具委派给下属 5 个 SubAgent |
| `fae:planning` | 决策 | goal_parsing / plan_design / plan_review / plan_store |
| `fae:insight` | 决策 | insight_plan / insight_decompose / insight_query / insight_nl2code / insight_reflect / insight_report |
| `fae:provisioning-wifi` | 执行 | wifi_simulation |
| `fae:provisioning-delivery` | 执行 | experience_assurance |
| `fae:provisioning-cei-chain` | 执行 | cei_pipeline / cei_score_query / fault_diagnosis / remote_optimization |

## Skill 调用约定

Agent 通过 free-code 的 Bash / Read 工具调用 Skill（不需要 agno 那套 `get_skill_*` 间接层）：

```bash
# 1. 加载 Skill 指令
Read: $CC_BRIDGE_FREE_CODE_PLUGIN_DIR/skills/<name>/SKILL.md

# 2. 按需读取参考文件
Read: $CC_BRIDGE_FREE_CODE_PLUGIN_DIR/skills/<name>/references/<ref>

# 3. 执行 Python 脚本（cwd 为 plugin 根目录，激活 venv）
Bash: cd "$CC_BRIDGE_FREE_CODE_PLUGIN_DIR" && uv run python skills/<name>/scripts/<script>.py '<json_args>'
```

`CC_BRIDGE_FREE_CODE_PLUGIN_DIR` 由 Hummingbird cc-bridge 透传给 free-code 子进程。

## 本地准备

```bash
# 1. 安装依赖（vendor editable 包 + Python 库）
uv sync

# 2. 配置 FAE 凭证（如需运行 Provisioning skills）
cp fae_poc/config.ini.example fae_poc/config.ini
# 编辑 config.ini，并把本地 NCELogin.py 复制到 fae_poc/NCELogin.py
```

## 开发约束

参考 [.claude/rules/skills_rules.md](.claude/rules/skills_rules.md)（Skills 设计范式规范）。

- **决策型 Agent**（Planning / Insight）— 产出方案或报告，不执行 Provisioning
- **执行型 Agent**（Provisioning × 3）— 接收载荷调用对应 Skill，不做业务规则判断
- **Orchestrator** — 仅负责路由 + 派发，不推导 Skill 参数（参数提取是 Provisioning 的职责）
- 3 个 Provisioning Agent 的 system prompt 内容相似，按各自专业方向独立内联在 `agents/provisioning-*.md`，不再共享外部 prompt 文件
