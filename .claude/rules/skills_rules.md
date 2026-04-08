# Skills 开发规范

> 遵循 [Google ADK 5 Agent Skills Design Patterns](https://lavinigam.com/posts/adk-skill-design-patterns/)

## 1. ADK 5 范式映射

所有 Skill 必须对应以下 5 种范式之一，并在 SKILL.md frontmatter 中声明 `paradigm` 字段：

| 范式 | 说明 | 本项目 Skill |
|---|---|---|
| **Tool Wrapper** | 封装已有 API/库，将最佳实践注入指令 | `data_insight` |
| **Generator** | 从模板生成结构化输出（含 Jinja2 渲染） | `solution_generation`、`report_generation`、`cei_config`、`wifi_simulation`、`fault_config`、`remote_loop` |
| **Reviewer** | 按清单评估内容并输出评分报告 | `solution_verification` |
| **Inversion** | 先访谈再执行（Agent 主导提问，收集完整信息后才行动） | `slot_filling` |
| **Pipeline** | 强制多步骤顺序执行，含中间质量门控 | 整体三类任务流程编排 |

## 2. Agno 目录约定

agno 的 `LocalSkills` 加载器只扫描固定子目录，目录名必须严格匹配：

```
skill_name/
├── SKILL.md          # 必须：YAML frontmatter（name/description）+ Markdown 指令体
├── scripts/          # 可选：Python 可执行脚本（agno 扫描 → available_scripts）
└── references/       # 可选：参考文件（配置示例、Jinja2 模板、Schema 等）
                      #         agno 扫描 → available_references
```

**关键约束**：

- `templates/` 目录名 **不被** agno 扫描 → 统一改用 `references/`
- Skill 顶层散落文件（如裸放的 `.yaml` / `.json`）**对 LLM 不可见** → 必须放入 `references/`
- `scripts/` 中的文件名通过 `available_scripts` 字段暴露给 LLM
- `references/` 中的文件名通过 `available_references` 字段暴露给 LLM

## 3. SKILL.md 编写规范

```markdown
---
name: skill_name
description: "一句话描述（L1 元数据，~100 token，Agent 启动时常驻加载）"
---

## Metadata
- **paradigm**: 对应 ADK 范式名称（必填）
- **when_to_use**: 触发条件（一句话）
- **inputs**: 输入数据类型
- **outputs**: 输出数据类型

## When to Use
- ✅ 适用场景
- ❌ 不适用场景

## How to Use
（具体调用步骤；LLM 按需通过 get_skill_instructions 加载，即 L2）

## Scripts / References
（列出 scripts/ 和 references/ 中的文件及其用途）

## Examples
（输入/输出示例）
```

**Generator 范式额外要求**（渲染类脚本）：

- How to Use 中必须明确写出 `get_skill_script(..., execute=True)` 的调用方式
- 必须声明：脚本 `stdout` 即最终产物，Agent 须原样输出给用户，禁止二次改写

## 4. 渐进式披露（Progressive Disclosure）

| 层级 | 加载时机 | 内容 |
|---|---|---|
| L1（~100 token） | Agent 启动时常驻 | SKILL.md frontmatter（`name` + `description`） |
| L2（完整指令） | 决定使用该 Skill 时 | SKILL.md 正文，通过 `get_skill_instructions` 加载 |
| L3（资源文件） | 脚本运行时按需 | `references/` 文件内容，通过 `get_skill_reference` 加载 |

**系统提示与 SKILL.md 的职责边界**：

| 放系统提示（`prompts/main_agent_system.md`） | 放 SKILL.md |
|---|---|
| 协议级通用规则（调用顺序、输出格式、stdout 处理） | 技能专属规则（触发条件、调用步骤、模板说明） |
| 任务类型识别规则 | 当前 Skill 的禁止事项 |
| 跨 Skill 的流程状态机 | 范式声明与资源列表 |

> 禁止将某个 Skill 的专属行为写入系统提示 — 违反 Progressive Disclosure 原则。

## 5. Skill 开发禁止事项

- 不在 `skill_name/` 顶层放散落资源文件 → 放入 `references/`
- 不创建 `templates/` 子目录 → 统一用 `references/`
- 不在 Skill 脚本中感知 `session_id`（持久化由 core 层处理）
- SKILL.md frontmatter 缺少 `paradigm` 字段视为不合规
- Jinja2 渲染类脚本（Generator 范式）的 stdout 不得被 Agent 二次改写
- 不新增空 Skill 目录（无 SKILL.md 的目录不被 LocalSkills 识别，属无效目录）
