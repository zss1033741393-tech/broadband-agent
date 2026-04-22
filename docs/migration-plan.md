# 家宽网络调优助手 — Agno → OpenCode 迁移方案

> **文档版本**: v1.1  
> **日期**: 2026-04-22  
> **范围**: 将现有 agno Team 多智能体架构迁移至 OpenCode 终端交互框架，验证 agent 角色和 skills 能力在 OpenCode 范式下的可行性  
> **运行环境**: Windows (原生 / WSL) + OpenCode TUI  
> **原则**: 配置层桥接，代码层零侵入；谁的功能改谁的文件，不耦合

---

## 1. 现状分析

### 1.1 当前架构概览

项目基于 agno 框架构建了一个 **Team (coordinate 模式) 多智能体系统**：

```
OrchestratorTeam (leader, coordinate 模式, prompts/orchestrator.md)
  ├─ PlanningAgent             (goal_parsing + plan_design + plan_review + plan_store)
  ├─ InsightAgent              (insight_plan + insight_decompose + insight_query
  │                             + insight_nl2code + insight_reflect + insight_report)
  ├─ ProvisioningWifiAgent     (wifi_simulation)
  ├─ ProvisioningDeliveryAgent (experience_assurance)
  └─ ProvisioningCeiChainAgent (cei_pipeline + cei_score_query
                                + fault_diagnosis + remote_optimization)
```

### 1.2 关键组件职责

| 组件 | 文件 | 职责 |
|------|------|------|
| agent_factory.py | `core/agent_factory.py` | 从 `configs/agents.yaml` 装配 Team + 5 SubAgent |
| model_loader.py | `core/model_loader.py` | 从 `configs/model.yaml` 创建 agno Model 实例 (OpenRouter/OpenAI/OpenAILike) |
| session_manager.py | `core/session_manager.py` | session_hash → Team + Tracer 隔离 |
| LocalSkills | `skills/` 目录 | 10 个自包含 Skill，agno 自动扫描 SKILL.md + scripts/ + references/ |
| prompts/ | `prompts/*.md` | 4 份 SubAgent 作业手册 (orchestrator / planning / insight / provisioning) |
| agents.yaml | `configs/agents.yaml` | Team + 5 SubAgent 的 prompt/skills/description 声明 |

### 1.3 Skill 调用链 (agno 范式)

LLM 在 agno 框架内通过三个内置工具与 Skill 交互：

```
get_skill_instructions(skill_name)           → 读取 SKILL.md 正文 (L2 渐进加载)
get_skill_script(skill_name, script, execute=True, args=[...]) → 执行脚本，stdout 为结果
get_skill_reference(skill_name, ref_file)    → 读取 references/ 下的参考文件 (L3)
```

所有 skill 脚本均为 **CLI 风格** (接受命令行参数，输出 JSON 到 stdout)，这是迁移的最大利好。

---

## 2. 为什么选 OpenCode 而非 Claude Code

### 2.1 两者不能统一设计

| 维度 | OpenCode | Claude Code |
|------|----------|-------------|
| Agent 层级 | primary agent + subagent (Task tool 委派) | 单一 agent，无原生 subagent |
| 多 agent 协作 | Task tool 原生支持，subagent 独立 session/context | 需要 MCP server 或多进程模拟 |
| Skills 系统 | 原生 Skill tool，扫描 `.opencode/skills/` | 无原生 skill，依赖 `.claude/commands/` |
| 自定义工具 | `.opencode/tools/*.ts` 或 bash | MCP server |
| 模型灵活性 | 75+ provider，OpenRouter 原生支持 | 绑定 Anthropic 模型 |
| 项目规则 | AGENTS.md (兼容 CLAUDE.md 回退) | CLAUDE.md |

### 2.2 选择 OpenCode 的理由

1. **架构映射最直接**：agno Team (coordinate) ↔ OpenCode primary agent + subagent (Task tool)，一对一映射
2. **模型兼容**：项目当前使用 OpenRouter + qwen，OpenCode 原生支持 `openrouter/qwen/qwen3.5-27b`
3. **Skill 格式兼容**：OpenCode 的 skill 格式 (SKILL.md frontmatter) 与 agno LocalSkills 的格式完全一致
4. **终端优先**：OpenCode 的 TUI 交互天然适合"在终端里验证 agent 角色和 skills 能力"的目标
5. **透明可控**：开源，配置暴露完整，调试迁移问题更快

---

## 3. 概念映射

### 3.1 核心概念对照

| Agno 概念 | OpenCode 等价物 | 说明 |
|-----------|-----------------|------|
| Team leader (Orchestrator) | Build primary agent + AGENTS.md | Orchestrator 的路由逻辑写入 primary agent prompt |
| SubAgent (member) | Subagent (`.opencode/agents/*.md`) | 每个 subagent 一个 `.md` 文件 |
| Team.arun (coordinate 模式) | Task tool (subagent delegation) | primary agent 通过 Task tool 把任务委派给 subagent |
| LocalSkills (SKILL.md) | Skill tool (`.opencode/skills/`) | frontmatter 格式完全一致 |
| `get_skill_script(execute=True)` | Bash tool (`python scripts/*.py`) | 脚本本身不改，调用方式从 agno 工具改为 bash 命令 |
| `get_skill_instructions` | Skill tool (加载 SKILL.md) | OpenCode 原生支持 |
| `get_skill_reference` | Read tool (`skills/*/references/*`) | 改为直接 Read 文件路径 |
| `configs/model.yaml` | `opencode.json` model + provider | provider/model/api_key 映射 |
| `system_message` (prompt) | Agent prompt (`.md` 文件内容) | Markdown 内容直接嵌入 agent `.md` 文件 |
| `agents.yaml` skills 子集 | Agent `.md` frontmatter + prompt 声明 | 每个 agent prompt 里声明可用 skill 列表 |
| `session_id` + SQLite | OpenCode 内置 session (SQLite) | 终端验证阶段不做持久化对齐 |
| Gradio UI / FastAPI | OpenCode TUI / headless API | 验证阶段仅用 TUI；原有 UI 通道保留不动 |

### 3.2 Skill 调用语法转换

**agno 格式 → OpenCode 格式**，以 `goal_parsing` 为例：

```markdown
# ─── agno (原来) ───

## 加载指令
get_skill_instructions("goal_parsing")

## 执行脚本
get_skill_script("goal_parsing", "slot_engine.py", execute=True, args=["<user_input>", "<state_json>"])

## 读取参考
get_skill_reference("plan_design", "examples.md")
```

```markdown
# ─── OpenCode (改后) ───

## 加载指令
使用 Skill tool 加载 goal_parsing 的 SKILL.md

## 执行脚本
使用 Bash tool 执行：
python skills/goal_parsing/scripts/slot_engine.py "<user_input>" "<state_json>"

## 读取参考
使用 Read tool 读取：
skills/plan_design/references/examples.md
```

> **关键**：`skills/*/scripts/` 下的所有 Python 脚本 **不需要任何修改**。它们本来就是 CLI 风格 (argparse / sys.argv + stdout JSON)，通过 bash 直接调用完全兼容。

---

## 4. 目标目录结构

迁移后项目根目录新增 `.opencode/` 配置层，**不动现有任何文件**：

```
project-root/
│
├── .opencode/                          # ← 新增：OpenCode 配置层
│   ├── agents/                         #    agent 角色定义
│   │   ├── orchestrator.md             #    primary agent (Orchestrator)
│   │   ├── planning.md                 #    subagent (方案规划)
│   │   ├── insight.md                  #    subagent (数据洞察)
│   │   ├── provisioning-wifi.md        #    subagent (WiFi 仿真)
│   │   ├── provisioning-delivery.md    #    subagent (差异化承载)
│   │   └── provisioning-cei-chain.md   #    subagent (体验保障链)
│   │
│   └── skills/                         #    Junction 指向 ../skills (见 §4.1)
│
├── opencode.json                       # ← 新增：OpenCode 项目配置
├── AGENTS.md                           # ← 新增：项目级规则 (可复用 CLAUDE.md)
│
│   ──── 以下全部保留不动 ────
├── configs/
│   ├── model.yaml                      #    agno 模型配置 (保留)
│   ├── agents.yaml                     #    agno Team 配置 (保留)
│   └── downstream.yaml                 #    下游接口配置 (保留)
├── core/                               #    agno 核心逻辑 (保留)
├── prompts/                            #    原始 prompt 文件 (保留，作为 source of truth)
│   ├── orchestrator.md
│   ├── planning.md
│   ├── insight.md
│   └── provisioning.md
├── skills/                             #    10 个 Skill 目录 (不动)
│   ├── goal_parsing/
│   ├── plan_design/
│   ├── plan_review/
│   ├── plan_store/
│   ├── insight_plan/
│   ├── insight_decompose/
│   ├── insight_query/
│   ├── insight_nl2code/
│   ├── insight_reflect/
│   ├── insight_report/
│   ├── wifi_simulation/
│   ├── experience_assurance/
│   ├── cei_pipeline/
│   ├── cei_score_query/
│   ├── fault_diagnosis/
│   └── remote_optimization/
├── ui/                                 #    Gradio UI (保留)
├── api/                                #    FastAPI (保留)
└── vendor/                             #    子包 (保留)
```

### 4.1 Windows 环境下 skills 目录挂载

OpenCode 的 Skill tool 只扫描 `.opencode/skills/`（项目级）和 `~/.config/opencode/skills/`（全局级）。项目现有 `skills/` 在根目录，需要让 `.opencode/skills/` 指向它。

**Linux/macOS** 用软链即可：`ln -s ../skills .opencode/skills`

**Windows 上有三种方案**，按推荐顺序：

#### 方案 A：Junction（目录联接，推荐）

Junction 是 Windows 原生的目录级链接，**不需要管理员权限**，不需要开启开发者模式，对所有程序透明可见——OpenCode、Python、Git 都能正常读取。

```powershell
# PowerShell（在项目根目录执行）
cmd /c mklink /J .opencode\skills skills
```

或者在 cmd 里：

```cmd
cd your-project-root
mklink /J .opencode\skills skills
```

执行后 `.opencode\skills\goal_parsing\SKILL.md` 等路径直接可达，和 Linux 软链行为完全一致。

> **注意**：Junction 的 target 必须是**绝对路径**或相对于当前 cmd 工作目录的路径（不是相对于 junction 自身位置）。最保险的写法：
> ```cmd
> mklink /J .opencode\skills %cd%\skills
> ```
> 这会展开为绝对路径，避免歧义。

**Git 处理**：Junction 在 Git 里表现为一个普通目录，`.gitignore` 中添加 `.opencode/skills` 避免重复追踪。

#### 方案 B：WSL（Windows Subsystem for Linux）

OpenCode 官方推荐 Windows 用户通过 WSL 使用。WSL 下可以直接用 `ln -s`，且 Python 环境管理更顺畅：

```bash
# 在 WSL 中
cd /mnt/c/Users/you/projects/your-project   # 访问 Windows 盘上的项目
ln -s ../skills .opencode/skills             # 标准软链
opencode                                     # 直接启动
```

WSL 的优势是文件系统行为和 Linux 完全一致，缺点是需要在 WSL 环境里也装好 Python + uv + 项目依赖。

#### 方案 C：复制脚本自动同步

如果 Junction 和 WSL 都不方便，用一个 Python 脚本把 `skills/` 的 **SKILL.md + references/** 同步到 `.opencode/skills/`：

```python
# scripts/sync_skills_to_opencode.py
"""将 skills/ 的元数据同步到 .opencode/skills/。
仅同步 SKILL.md 和 references/（OpenCode Skill tool 只需要这些）。
scripts/ 不需要复制 —— 通过 Bash tool 直接从 skills/ 根路径执行。
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "skills"
DST = ROOT / ".opencode" / "skills"

def sync():
    DST.mkdir(parents=True, exist_ok=True)
    for skill_dir in sorted(SRC.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        dst_skill = DST / skill_dir.name
        dst_skill.mkdir(exist_ok=True)
        shutil.copy2(skill_md, dst_skill / "SKILL.md")
        refs_src = skill_dir / "references"
        if refs_src.is_dir():
            refs_dst = dst_skill / "references"
            if refs_dst.exists():
                shutil.rmtree(refs_dst)
            shutil.copytree(refs_src, refs_dst)

if __name__ == "__main__":
    sync()
    print(f"Synced {SRC} -> {DST}")
```

> **关键**：方案 C 只复制 `SKILL.md` 和 `references/`（供 Skill tool 发现和加载），**不复制 `scripts/`**。脚本始终通过 Bash tool 从 `skills/*/scripts/` 直接执行，避免路径歧义和双份维护。

#### 方案对比

| 维度 | A: Junction | B: WSL | C: 复制脚本 |
|------|-------------|--------|------------|
| 是否需要管理员 | ❌ 不需要 | ❌（WSL 已装好时） | ❌ 不需要 |
| 是否实时同步 | ✅ 透明零延迟 | ✅ 软链透明 | ❌ 需重跑脚本 |
| Git 友好性 | ⚠️ 需 .gitignore | ✅ 标准软链 | ⚠️ 需 .gitignore |
| Python 环境 | ✅ 复用 Windows | ⚠️ 需 WSL 装一套 | ✅ 复用 Windows |
| Bash tool 脚本路径 | `python skills/…` | `python skills/…` | `python skills/…` |
| 推荐场景 | **日常开发首选** | 已有 WSL 环境时 | Junction 不可用时兜底 |

---

## 5. 各配置文件详细设计

### 5.1 `opencode.json` — 项目配置

```json
{
  "model": "openrouter/qwen/qwen3.5-27b",
  "provider": {
    "openrouter": {
      "options": {
        "apiKey": "{env:OPENROUTER_API_KEY}"
      }
    }
  },
  "permission": {
    "bash": "allow",
    "edit": "deny",
    "skill": "allow",
    "task": "allow",
    "read": "allow",
    "glob": "allow",
    "grep": "allow",
    "webfetch": "deny"
  },
  "instructions": [
    "prompts/orchestrator.md"
  ]
}
```

**与 `configs/model.yaml` 的映射**：

| model.yaml 字段 | opencode.json 字段 |
|------------------|-------------------|
| `provider: openrouter` | `"model": "openrouter/..."` |
| `base_url` | OpenCode 内置 OpenRouter 支持，无需配置 |
| `api_key_env: OPENROUTER_API_KEY` | `"apiKey": "{env:OPENROUTER_API_KEY}"` |
| `model: qwen/qwen3.5-27b` | `"model": "openrouter/qwen/qwen3.5-27b"` |
| `temperature: 0.3` | 在 agent `.md` frontmatter 中 `temperature: 0.3` |
| `role_map` | OpenCode 自动处理 |

### 5.2 `AGENTS.md` — 项目级规则

```markdown
# 家宽网络调优智能助手

## 项目概述
基于多智能体架构的家宽网络调优系统，包含 1 个 Orchestrator + 5 个 SubAgent + 16 个业务 Skills。

## 环境准备
- Python 3.11+，使用 uv 管理依赖
- 启动前执行 `uv sync` 安装全部依赖（含 vendor/ce_insight_core editable 安装）
- 所有 skill 脚本在 `skills/*/scripts/` 目录，通过 bash 直接调用
- 下游接口 mock/real 切换见 `configs/downstream.yaml`

## Skill 脚本调用规范
- 脚本参数为 JSON 字符串，通过命令行参数传入
- 脚本输出为 JSON 到 stdout，作为最终结果
- Generator 范式脚本的 stdout **禁止二次改写**，须原样输出
- 调用形式：`python skills/<skill_name>/scripts/<script>.py <args...>`

## Agent 协作规则
- 决策型 Agent (Planning / Insight) 产出方案或报告，**不执行**配置下发
- 执行型 Agent (Provisioning ×3) 接收任务载荷后按 Skill schema 提参并调用，**不做业务规则判断**
- Orchestrator 负责路由和结果汇总，不直接调用 Skill 脚本

## 目录说明
- `skills/` — 16 个自包含 Skill，每个含 SKILL.md + scripts/ + references/
- `prompts/` — 4 份 Agent 作业手册 (source of truth)
- `configs/` — 模型/团队/下游接口配置
- `vendor/` — ce_insight_core 等内部依赖
```

### 5.3 Primary Agent — `.opencode/agents/orchestrator.md`

```markdown
---
description: >
  家宽网络调优 Orchestrator：识别用户意图，路由到正确的专家 agent，
  拆分复合任务，汇总执行结果。不直接调用 Skill 脚本。
mode: primary
model: openrouter/qwen/qwen3.5-27b
temperature: 0.3
permission:
  task: allow
  bash: deny
  skill: allow
  edit: deny
  read: allow
permission.task:
  planning: allow
  insight: allow
  provisioning-wifi: allow
  provisioning-delivery: allow
  provisioning-cei-chain: allow
---

（此处嵌入 prompts/orchestrator.md 的完整内容）

## 重要：Agent 委派语法

当需要委派任务时，使用 Task tool：

- 方案规划任务 → 委派给 @planning
- 数据洞察任务 → 委派给 @insight
- WiFi 仿真任务 → 委派给 @provisioning-wifi
- 差异化承载任务 → 委派给 @provisioning-delivery
- CEI 体验保障链任务 → 委派给 @provisioning-cei-chain

委派时将完整的任务描述和上下文传递给对应 subagent。
```

> **适配要点**：将原 `prompts/orchestrator.md` 中"交给 PlanningAgent"之类的表述统一改为"使用 Task tool 委派给 @planning"。路由逻辑和意图识别规则 **内容不变**，只改委派动词。

### 5.4 Subagent — `.opencode/agents/planning.md`

```markdown
---
description: >
  方案规划专家：目标解析(goal_parsing) + 方案设计(plan_design)
  + 方案评审(plan_review) + 方案持久化(plan_store)，
  产出分段 Markdown 方案。
mode: subagent
model: openrouter/qwen/qwen3.5-27b
temperature: 0.3
permission:
  bash: allow
  skill: allow
  edit: deny
  read: allow
---

（此处嵌入 prompts/planning.md 的完整内容）

## 可用 Skills
- goal_parsing — 槽位追问引擎
- plan_design — 方案设计 (Instructional, 无脚本)
- plan_review — 方案评审
- plan_store — 方案持久化

## Skill 调用方式 (OpenCode 适配)

### 加载 Skill 指令
使用 Skill tool 加载对应 skill 的 SKILL.md。

### 执行脚本
使用 Bash tool：
- `python skills/goal_parsing/scripts/slot_engine.py "<user_input>" "<state_json>"`
- `python skills/plan_review/scripts/checker.py "<plan_markdown_string>"`
- `python skills/plan_store/scripts/save_plan.py "<plan_text>"`
- `python skills/plan_store/scripts/read_plan.py`

### 读取参考文件
使用 Read tool：
- `skills/plan_design/references/examples.md`
```

### 5.5 Subagent — `.opencode/agents/insight.md`

```markdown
---
description: >
  数据洞察分析师：按 Plan→Decompose→Execute→Reflect→Report 五阶段
  产出数据洞察报告，接入 ce_insight_core 真实计算内核。
mode: subagent
model: openrouter/qwen/qwen3.5-27b
temperature: 0.3
permission:
  bash: allow
  skill: allow
  edit: deny
  read: allow
---

（此处嵌入 prompts/insight.md 的完整内容）

## 可用 Skills
- insight_plan — 洞察计划
- insight_decompose — 任务分解
- insight_query — 数据查询 + 洞察函数
- insight_nl2code — NL2Code 沙箱
- insight_reflect — 阶段反思
- insight_report — 报告生成

## Skill 调用方式 (OpenCode 适配)

### 执行脚本（使用 Bash tool）
- `python skills/insight_plan/scripts/build_macro_plan.py "<payload_json>"`
- `python skills/insight_decompose/scripts/decompose.py "<payload_json>"`
- `python skills/insight_query/scripts/run_query.py "<payload_json>"`
- `python skills/insight_query/scripts/run_insight.py "<payload_json>"`
- `python skills/insight_query/scripts/list_schema.py "<payload_json>"`
- `python skills/insight_nl2code/scripts/run_nl2code.py "<payload_json>"`
- `python skills/insight_report/scripts/build_report.py "<payload_json>"`

### 读取参考文件（使用 Read tool）
- `skills/insight_query/references/insight_functions.md`
- `skills/insight_nl2code/references/nl2code_spec.md`
```

### 5.6 Subagent — `.opencode/agents/provisioning-wifi.md`

```markdown
---
description: >
  WIFI 仿真执行专家：驱动户型图识别→热力图→RSSI 采集→选点对比 4 步流水线。
  接收 PlanningAgent 产出的 WIFI 仿真段方案，按 Skill schema 提参并执行。
mode: subagent
model: openrouter/qwen/qwen3.5-27b
temperature: 0.3
permission:
  bash: allow
  skill: allow
  edit: deny
  read: allow
---

（此处嵌入 prompts/provisioning.md 的完整内容）

## 专业方向
WIFI 仿真执行专家：驱动户型图识别→热力图→RSSI 采集→选点对比 4 步流水线。

## 可用 Skills
- wifi_simulation — WiFi 信号仿真

## Skill 调用方式 (OpenCode 适配)
使用 Bash tool 执行：
- `python skills/wifi_simulation/scripts/<script>.py <args...>`

具体脚本和参数见 wifi_simulation/SKILL.md。
```

### 5.7 Subagent — `.opencode/agents/provisioning-delivery.md`

```markdown
---
description: >
  差异化承载执行专家：切片配置与应用白名单 (Appflow / 抖音切片等)，
  底层调用 FAN 网络切片服务 experience_assurance 接口。
mode: subagent
model: openrouter/qwen/qwen3.5-27b
temperature: 0.3
permission:
  bash: allow
  skill: allow
  edit: deny
  read: allow
---

（此处嵌入 prompts/provisioning.md 的完整内容）

## 专业方向
差异化承载执行专家：切片配置与应用白名单。

## 可用 Skills
- experience_assurance — 差异化承载

## Skill 调用方式 (OpenCode 适配)
使用 Bash tool 执行：
- `python skills/experience_assurance/scripts/<script>.py <args...>`

具体脚本和参数见 experience_assurance/SKILL.md。
```

### 5.8 Subagent — `.opencode/agents/provisioning-cei-chain.md`

```markdown
---
description: >
  体验保障链执行专家：CEI 权重配置 → CEI 评分回采 → 故障诊断 → 远程闭环
  的顺序串行 workflow，每步基于上一步上下文自适应推导参数。
mode: subagent
model: openrouter/qwen/qwen3.5-27b
temperature: 0.3
permission:
  bash: allow
  skill: allow
  edit: deny
  read: allow
---

（此处嵌入 prompts/provisioning.md 的完整内容）

## 专业方向
体验保障链执行专家：CEI 权重配置 → CEI 评分回采 → 故障诊断 → 远程闭环。

## 可用 Skills
- cei_pipeline — CEI 权重配置下发
- cei_score_query — CEI 评分查询
- fault_diagnosis — 故障诊断
- remote_optimization — 远程闭环优化

## Skill 调用方式 (OpenCode 适配)
使用 Bash tool 执行：
- `python skills/cei_pipeline/scripts/cei_threshold_config.py <args...>`
- `python skills/cei_score_query/scripts/<script>.py <args...>`
- `python skills/fault_diagnosis/scripts/fault_diagnosis.py <args...>`
- `python skills/remote_optimization/scripts/manual_batch_optimize.py <args...>`

具体参数 schema 见各 Skill 的 SKILL.md。
```

---

## 6. SKILL.md 适配规则

### 6.1 原则

每个 SKILL.md 的 **frontmatter 和正文内容保持不变**，只需要在 "How to Use" 部分追加一段 OpenCode 兼容的调用说明。采用"双模式声明"策略，让同一份 SKILL.md 同时服务 agno 和 OpenCode：

```markdown
## How to Use

### agno 调用方式
（保留原有的 get_skill_script / get_skill_instructions / get_skill_reference 说明）

### OpenCode 调用方式
使用 Bash tool 执行：
`python skills/goal_parsing/scripts/slot_engine.py "<user_input>" "<state_json>"`

使用 Read tool 读取参考：
`skills/goal_parsing/references/<file>`
```

### 6.2 逐 Skill 适配清单

| Skill | 范式 | 有脚本 | 主要脚本 | OpenCode Bash 调用形式 |
|-------|------|--------|----------|----------------------|
| goal_parsing | Inversion | ✅ | `slot_engine.py` | `python skills/goal_parsing/scripts/slot_engine.py "<input>" "<state>"` |
| plan_design | Instructional | ❌ | 无 (纯 LLM 推理) | 无需 bash，Skill tool + Read tool 即可 |
| plan_review | Reviewer | ✅ | `checker.py` | `python skills/plan_review/scripts/checker.py "<plan_md>"` |
| plan_store | Tool Wrapper | ✅ | `save_plan.py` / `read_plan.py` | `python skills/plan_store/scripts/save_plan.py "<text>"` |
| insight_plan | Pipeline | ✅ | `build_macro_plan.py` | `python skills/insight_plan/scripts/build_macro_plan.py "<json>"` |
| insight_decompose | Pipeline | ✅ | `decompose.py` | `python skills/insight_decompose/scripts/decompose.py "<json>"` |
| insight_query | Tool Wrapper | ✅ | `run_query.py` / `run_insight.py` / `list_schema.py` | `python skills/insight_query/scripts/run_insight.py "<json>"` |
| insight_nl2code | Tool Wrapper | ✅ | `run_nl2code.py` | `python skills/insight_nl2code/scripts/run_nl2code.py "<json>"` |
| insight_reflect | Pipeline | ✅ | (视实现) | `python skills/insight_reflect/scripts/<script>.py "<json>"` |
| insight_report | Generator | ✅ | `build_report.py` | `python skills/insight_report/scripts/build_report.py "<json>"` |
| wifi_simulation | Pipeline+Generator | ✅ | (多脚本) | 见 SKILL.md 具体声明 |
| experience_assurance | Tool Wrapper | ✅ | (视实现) | 见 SKILL.md 具体声明 |
| cei_pipeline | Tool Wrapper | ✅ | `cei_threshold_config.py` | `python skills/cei_pipeline/scripts/cei_threshold_config.py "<json>"` |
| cei_score_query | Tool Wrapper | ✅ | (视实现) | 见 SKILL.md 具体声明 |
| fault_diagnosis | Tool Wrapper | ✅ | `fault_diagnosis.py` | `python skills/fault_diagnosis/scripts/fault_diagnosis.py "<json>"` |
| remote_optimization | Tool Wrapper | ✅ | `manual_batch_optimize.py` | `python skills/remote_optimization/scripts/manual_batch_optimize.py --strategy <s> ...` |

---

## 7. Prompt 适配规则

### 7.1 orchestrator.md 改动清单

只改委派动词，不改路由逻辑：

| 原文 (agno) | 改为 (OpenCode) |
|-------------|-----------------|
| "交给 PlanningAgent" / "转给 Planning" | "使用 Task tool 委派给 @planning" |
| "派发给 InsightAgent" | "使用 Task tool 委派给 @insight" |
| "转给 ProvisioningWifiAgent" | "使用 Task tool 委派给 @provisioning-wifi" |
| "转给 ProvisioningDeliveryAgent" | "使用 Task tool 委派给 @provisioning-delivery" |
| "转给 ProvisioningCeiChainAgent" | "使用 Task tool 委派给 @provisioning-cei-chain" |

### 7.2 planning.md / insight.md / provisioning.md 改动清单

将 Skill 工具调用语法从 agno 格式改为 bash 格式：

| 原文 (agno) | 改为 (OpenCode) |
|-------------|-----------------|
| `get_skill_instructions("goal_parsing")` | 使用 Skill tool 加载 goal_parsing |
| `get_skill_script("goal_parsing", "slot_engine.py", execute=True, args=[...])` | 使用 Bash tool：`python skills/goal_parsing/scripts/slot_engine.py <args...>` |
| `get_skill_reference("plan_design", "examples.md")` | 使用 Read tool：`skills/plan_design/references/examples.md` |

### 7.3 共享 prompt 的处理

当前 3 个 Provisioning 实例共享 `prompts/provisioning.md`，通过 `agents.yaml` 的 `description` 字段区分职责。在 OpenCode 里：

- `prompts/provisioning.md` 原文件 **不动** (source of truth)
- 3 个 `.opencode/agents/provisioning-*.md` 各自复制一份内容
- 通过 frontmatter 的 `description` 和正文末尾的 "可用 Skills" 列表区分职责
- 如果 `provisioning.md` 后续有改动，3 份 agent `.md` 需要同步更新（可用脚本自动化）

---

## 8. 分阶段实施计划

### Phase 1 — 最小可运行 (1-2 天)

**目标**：验证单 agent + 单 skill 的完整链路

1. 安装 OpenCode：
   - Windows (推荐)：`npm i -g opencode-ai@latest` 或 `scoop install opencode`
   - WSL / macOS / Linux：`curl -fsSL https://opencode.ai/install | bash`
2. 配置 provider：`opencode auth login` → 选择 OpenRouter → 输入 API Key
3. 创建 `opencode.json`，配置模型和权限
4. 创建 `AGENTS.md`，写入项目概述和环境说明
5. 挂载 skills 目录（详见 §4.1）：
   - Windows 首选 Junction：`cmd /c mklink /J .opencode\skills %cd%\skills`
   - 或 WSL 软链：`ln -s ../skills .opencode/skills`
   - 或兜底复制：`python scripts/sync_skills_to_opencode.py`
6. 创建 `.opencode/agents/orchestrator.md` (primary)，先**不加 subagent 委派**，只做单 agent 直接调用 skill
7. 改写 `goal_parsing/SKILL.md` 的 "How to Use"，追加 OpenCode 调用说明
8. 终端运行 `opencode`，测试：用户输入 → Orchestrator 加载 goal_parsing skill → bash 执行 slot_engine.py → 返回追问

**验收标准**：
- `slot_engine.py` 通过 bash 执行成功，stdout JSON 被 LLM 正确解析
- LLM 能正确读取 SKILL.md 并按指令调用脚本

### Phase 2 — 多 agent 委派 (2-3 天)

**目标**：验证 Orchestrator → SubAgent → Skill 的三层委派

9. 创建 `.opencode/agents/planning.md` (subagent)
10. 在 orchestrator.md 中添加 Task tool 委派指令
11. 测试：用户输入 → Orchestrator 路由 → @planning → goal_parsing → slot_engine.py → 追问
12. 验证 Planning 的完整流程：goal_parsing → plan_design → plan_review
13. 逐个添加 insight + 3 个 provisioning subagent
14. 测试各 subagent 的独立 skill 调用

**验收标准**：
- Task tool 能正确委派到自定义 subagent
- Subagent 在独立 context 中完成 skill 调用并返回结果
- Orchestrator 能汇总 subagent 返回的结果

### Phase 3 — 全量迁移 + 端到端 (3-5 天)

**目标**：所有 agent + 所有 skill 的完整业务场景验证

15. 批量改写剩余 SKILL.md 的调用语法
16. 端到端测试：
    - 方案规划场景 (Planning 全流程)
    - 数据洞察场景 (Insight 五阶段)
    - WiFi 仿真场景
    - 差异化承载场景
    - CEI 体验保障链场景 (4 步串行)
    - 复合任务拆分场景 (Orchestrator → 多 agent 并行/串行)
17. 记录与 agno 的行为差异，标注需要调优的 prompt 细节

**验收标准**：
- 所有 16 个 skill 的脚本都能通过 bash 正常执行
- 5 个业务场景的端到端流程与 agno 版本行为一致
- Orchestrator 的路由准确率与 agno coordinate 模式相当

---

## 9. 已知风险与对策

### 9.1 Task tool 对自定义 subagent 的支持

**风险**：OpenCode 截至 v1.3.x，自定义 subagent 通过 Task tool 委派的支持不完全稳定 (GitHub issue #14308、#20059)。可能出现自定义 agent 不在 Task tool 的候选列表中。

**对策 A**：在 `opencode.json` 的 `agents` 配置里定义 agent（JSON 格式优先级高于 `.md` 文件）：
```json
{
  "agents": {
    "planning": {
      "prompt": ".opencode/agents/planning.md",
      "model": "openrouter/qwen/qwen3.5-27b",
      "mode": "subagent",
      "permission": { "bash": "allow", "edit": "deny" }
    }
  }
}
```

**对策 B**：如果 Task tool 确实不可用，退化为 **"单 agent + 多 skill"** 模式 —— 把所有 subagent 的能力折叠进 orchestrator 的 prompt 里，用 skill 区分职责而非 agent 区分。这会丢失 context 隔离，但功能上等价。

### 9.2 Windows 下 Skill 路径与 Junction

**风险**：OpenCode 的 Skill tool 期望 skill 在 `.opencode/skills/` 下。Windows 上 `ln -s` 软链需要开发者模式或管理员权限，可能不可用。

**对策**：
- **首选 Junction**（`mklink /J`）：不需要管理员权限，对 OpenCode 完全透明。详见 §4.1 方案 A。
- **Bash tool 路径不受影响**：无论用哪种挂载方案，脚本执行始终用 `python skills/<n>/scripts/<script>.py`（从项目根目录出发）。Skill tool 走 `.opencode/skills/`，Bash tool 走 `skills/`，两条路径各管各的。
- **路径分隔符**：prompt 里统一用 `/`。Python 在 Windows 上两种分隔符都认，不影响脚本执行。

### 9.3 Windows 上 OpenCode 的 Shell 配置

**风险**：OpenCode 的 Bash tool 在 Windows 上默认使用 `SHELL` 环境变量指定的 shell。如果未设置，可能回退到不支持某些语法的 shell。

**对策**：在 `opencode.json` 中显式配置 shell：

```json
{
  "shell": ["powershell.exe", "-NoProfile", "-Command"]
}
```

如果使用 Git Bash 或 WSL 则无需额外配置。

### 9.4 Python 环境依赖

**风险**：skill 脚本依赖 `vendor/ce_insight_core` 等 editable 安装的包，OpenCode bash 执行时需要这些包在 Python path 上。

**对策**：在 AGENTS.md 中声明"执行脚本前先运行 `uv sync`"。或者在 `.opencode/hooks/` 中配置 session 启动钩子自动执行环境检查。

### 9.5 Provisioning 共享 prompt 的同步维护

**风险**：`prompts/provisioning.md` 更新后，3 个 `.opencode/agents/provisioning-*.md` 需要手动同步。

**对策**：编写一个同步脚本 `scripts/sync_opencode_agents.py`，从 `prompts/*.md` + `configs/agents.yaml` 自动生成 `.opencode/agents/*.md`：

```python
# 伪代码
for agent_name, agent_cfg in agents_yaml["agents"].items():
    prompt_content = read(agent_cfg["prompt"])
    frontmatter = build_frontmatter(agent_name, agent_cfg)
    skills_section = build_skills_section(agent_cfg["skills"])
    write(f".opencode/agents/{agent_name}.md", frontmatter + prompt_content + skills_section)
```

### 9.6 stdout 事件协议 (insight 场景)

**风险**：insight 脚本通过 stdout 输出包含 `<!--event:step_result-->` 等标记的 JSON，agno 的 event_adapter.py 会解析这些标记。OpenCode 的 bash tool 只会把 stdout 原样返回给 LLM。

**对策**：这不影响功能正确性 —— LLM 仍然能看到完整的 stdout 并按 prompt 指令处理。只是不会有前端的进度条/图表渲染（这本来就不在终端验证的范围内）。

---

## 10. 不在本次迁移范围内的事项

| 事项 | 原因 |
|------|------|
| 前端 UI (Gradio / React) | 本次只验证终端交互，前端通道保留不动 |
| 会话持久化对齐 | OpenCode 有自己的 SQLite session，终端验证不需要跨 session |
| Observability (tracer / JSONL) | agno 的 trace 体系不迁移，OpenCode 有自己的 session stats |
| FastAPI 接口 | `api/` 层继续通过 agno bridge 工作，不受影响 |
| downstream_client.py | 下游 mock/real 切换逻辑在 skill 脚本内部，不涉及 agent 框架 |
| Claude Code 迁移 | 单独的后续项目，本文档仅覆盖 OpenCode |

---

## 11. 未来 Claude Code 迁移的初步思路

> 仅做记录，不作为本次执行范围。

Claude Code 没有原生的 subagent/Task tool 机制，多 agent 协作需要不同的方案：

1. **方案 A — MCP Server**：把每个 subagent 封装为 MCP server，Orchestrator 通过 MCP tool 调用
2. **方案 B — 多进程**：每个 subagent 是一个独立的 `claude` 进程，通过 `--print` 模式交互
3. **方案 C — 单 agent + 复合 prompt**：将所有角色折叠进一个 CLAUDE.md，用 skill 区分职责

预计 Claude Code 迁移的工作量是 OpenCode 的 2-3 倍，因为需要额外构建 agent 协作层。

---

## 12. 检查清单

### Phase 1 检查项
- [ ] `opencode.json` 创建完成，`opencode` 命令能正常启动
- [ ] OpenRouter provider 配置正确，LLM 能响应
- [ ] `.opencode/skills/` 挂载成功（Windows: Junction `mklink /J`；Linux/macOS: 软链）
- [ ] `goal_parsing/SKILL.md` 追加 OpenCode 调用说明
- [ ] `slot_engine.py` 通过 bash 执行正常，stdout JSON 正确

### Phase 2 检查项
- [ ] `.opencode/agents/` 下 6 个 agent `.md` 文件创建完成
- [ ] Orchestrator 能通过 Tab 键切换 / @ 提及 subagent
- [ ] Task tool 能委派到 @planning，subagent 独立执行
- [ ] Planning 全流程：goal_parsing → plan_design → plan_review 正常
- [ ] 5 个 subagent 的独立 skill 调用全部验证通过

### Phase 3 检查项
- [ ] 全部 16 个 SKILL.md 追加 OpenCode 调用说明
- [ ] 方案规划端到端场景通过
- [ ] 数据洞察端到端场景通过
- [ ] WiFi 仿真端到端场景通过
- [ ] 差异化承载端到端场景通过
- [ ] CEI 体验保障链端到端场景通过
- [ ] 复合任务拆分场景通过
- [ ] 同步脚本 `sync_opencode_agents.py` 编写完成
