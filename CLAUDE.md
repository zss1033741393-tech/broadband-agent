# CLAUDE.md

## 项目概述

家庭宽带 CEI 体验感知优化 Agent。基于 Agno 框架，多 Agent 协作完成从用户意图到设备配置的端到端生成。

核心模式：**OrchestratorTeam（主控）→ 4 个专家子 Agent → Skills 按需执行 → 产出持久化**

## 技术栈

Python 3.11+、Agno ≥ 2.5.14、FastAPI（AgentOS）、Gradio、SQLite、LanceDB

## 项目结构

```
broadband-agent/
├── configs/
│   ├── llm.yaml              # 模型配置（api_key / base_url / model / provider）
│   ├── pipeline.yaml         # 运行参数 + 各子 Agent 独立配置 + 存储路径
│   └── logging.yaml
├── app/
│   ├── main.py               # AgentOS 入口
│   ├── config.py             # YAML 加载（Pydantic，lru_cache 单例）
│   ├── agent/                # OrchestratorTeam + 4 个子 Agent + 共享工具
│   └── outputs/              # OutputSink：产出物持久化
├── skills/                   # 自包含 Skills，自动扫描（ADK 设计范式）
│   ├── intent_profiler/      # Inversion — 意图提取 + 画像推断补全 + 追问
│   ├── plan_generator/       # Generator — 五大方案模板并行填充
│   ├── constraint_checker/   # Reviewer  — 约束校验（强制步骤，最多重试 3 次）
│   ├── config_translator/    # Pipeline  — 语义方案 → 设备配置（NL2JSON）
│   └── domain_expert/        # Tool Wrapper — CEI 指标/设备能力矩阵/术语表
├── ui/chat_ui.py             # Gradio 调试界面（独立进程，不挂载到 AgentOS）
├── outputs/{session_id}/     # 运行时产出，gitignore
├── data/                     # SQLite + LanceDB，gitignore
└── tests/
```

## 架构设计原则

1. **Skills 自动扫描**：扫描 `skills/` 下含 `SKILL.md` 的子目录，不硬编码路径
2. **Agent 自主决策**：主控 system prompt 仅提供流程指导，不硬编排 Pipeline
3. **Skill 自包含**：模板、脚本、参考资料全在 Skill 内部，新增 Skill 无需改任何其他文件
4. **Skill 与模型解耦**：模型在 Agent 级注册，SKILL.md 不声明模型
5. **领域知识下沉**：domain_expert 挂载至全部子 Agent，按需加载，不走 RAG
6. **配置全在 YAML**：`configs/llm.yaml` 含 api_key，零硬编码，无 `.env`
7. **防编造机制**：工具返回 `error` 时必须停止并反馈用户，禁止跳过或自行编造数据
8. **Skills 与会话解耦**：脚本层不感知 session_id，持久化逻辑在 app 层

## Python 代码规范

- **文件头**：所有 `.py` 文件首行加 `from __future__ import annotations`
- **类型注解**：所有函数必须有完整类型注解（参数 + 返回值），使用内置泛型（`list[str]`、`dict[str, Any]`）
- **Docstring**：公开函数和类必须有 docstring，私有函数视复杂度决定
- **格式化**：`ruff format .`（双引号，行宽 100）
- **Lint**：`ruff check --fix .`（启用 E/F/I/UP 规则）
- **私有符号**：模块内部函数/变量以 `_` 开头
- **常量**：模块级常量全大写，放在 import 之后、函数之前

## Git 与提交规范

**Commit 类型：**
```
feat:     新功能
fix:      修复
refactor: 重构
docs:     文档
skill:    Skills 变更（SKILL.md / scripts / references）
```

**推送规则（重要）：**
- 必须使用 `git push -u origin <branch>` 通过 PAT URL 直接推送
- **严禁使用 GitHub MCP Server 工具（`mcp__github__push_files` 等）提交或推送代码**，速度极慢且不可靠
- 禁止 `--force` 推送到 main/master
- 推送后执行 `git fetch origin <branch>:refs/remotes/origin/<branch>` 同步本地跟踪引用

**README 同步规则：** 新增/删除模块、架构变更、目录结构变化、配置参数变更时必须同步更新 README.md；bug fix、测试补充、注释修改不需要。

## 开发纪律

- **改了 Web 相关代码必须真实启动验证**：修改 `app/main.py`、`ui/chat_ui.py` 后必须实际运行观察日志，不能只做静态分析
- **依赖 API 必须在沙箱安装后再写代码**：不能凭记忆猜第三方库的参数签名
- **设计文档只在本地维护**：`design.md` 及任何 `*_design.md` 禁止提交到版本库

## 常用命令

```bash
uvicorn app.main:app --reload --port 8000   # AgentOS API
python ui/chat_ui.py                        # Gradio 调试界面（另开终端）
pytest tests/ -v
ruff check --fix . && ruff format .
```

## 禁止事项

- 不要建 `app/tools/` 或顶层 `templates/` 目录
- 不要写 `skill_loader.py` 或 `tracer.py`，Agno 原生处理
- 不要在 `SKILL.md` 里加模型相关字段
- `constraint_checker` 是强制步骤，任何情况下不可跳过
