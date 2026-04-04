"""Agent 定义 — Agno 全能力集成

设计原则：
  - Skills 自动扫描发现，每个技能目录独立注册为 LocalSkills
  - LocalSkills 自动提供元工具：get_skill_instructions / get_skill_reference / get_skill_script
  - LLM 通过 get_skill_script(execute=True) 原生执行脚本，无需手写工具包装器
  - SYSTEM_PROMPT 只写行为引导，不硬编码技能名（技能列表由 <skills_system> 块动态注入）
  - Knowledge: LanceDB 向量存储领域知识，替代文件读取
  - Guardrails: PromptInjectionGuardrail 输入安全
  - Storage: P1（SqliteAgentStorage 待 agno.storage 模块稳定后启用）
  - User Memory: P1（enable_user_memories=True 待用户系统就绪后启用）
"""
from __future__ import annotations

import logging
from pathlib import Path

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.guardrails import PromptInjectionGuardrail
from agno.knowledge import Knowledge
from agno.models.openai import OpenAIChat
from agno.skills import LocalSkills, Skills
from agno.vectordb.lancedb import LanceDb
from app.config import LLMConfig

from app.config import load_config
from app.outputs.sink import get_current_session_id, output_sink_hook

logger = logging.getLogger("agent")

cfg = load_config()
SKILLS_DIR = Path(cfg.pipeline.skills_dir).resolve()


# ─────────────────────────────────────────────────────────────
# Skills 自动发现 — 每个技能目录独立注册
# LocalSkills 自动向 Agent 注入三个元工具：
#   get_skill_instructions(skill_name)
#   get_skill_reference(skill_name, reference_path)
#   get_skill_script(skill_name, script_path, execute=True, args=[...])
# ─────────────────────────────────────────────────────────────

def discover_skills(skills_dir: Path) -> Skills:
    """自动扫描 skills/ 下所有含 SKILL.md 的子目录，逐一注册为 LocalSkills"""
    loaders = []
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists():
            loaders.append(LocalSkills(path=str(child), validate=False))
    logger.info("发现 Skills: %s", [c.name for c in sorted(skills_dir.iterdir())
                                     if c.is_dir() and (c / "SKILL.md").exists()])
    return Skills(loaders=loaders)


# ─────────────────────────────────────────────────────────────
# Knowledge — 领域知识 RAG（LanceDB）
# domain_expert/references/ 中的文本类知识灌入向量库
# ─────────────────────────────────────────────────────────────

def _build_embedder():
    """按 provider 选择嵌入器

    openai / openai 兼容：OpenAILikeEmbedder，复用 llm.yaml 的 base_url + api_key
    anthropic：FastEmbedEmbedder（本地推理，无需 API key）
      需要安装：pip install fastembed
      首次运行自动下载模型（~100MB），之后离线可用
    """
    if cfg.llm.provider == "anthropic":
        from agno.knowledge.embedder.fastembed import FastEmbedEmbedder
        return FastEmbedEmbedder()
    # openai 兼容：复用 LLM 的 base_url（DeepSeek / OpenAI 均支持 embeddings 端点）
    from agno.knowledge.embedder.openai_like import OpenAILikeEmbedder
    return OpenAILikeEmbedder(
        id="text-embedding-3-small",
        api_key=cfg.llm.api_key,
        base_url=cfg.llm.base_url,
    )


def build_knowledge() -> Knowledge | None:
    """构建 LanceDB Knowledge，灌入 domain_expert/references/ 中的文本类文档

    使用 Knowledge.insert(path=..., skip_if_exists=True) 幂等灌入，
    避免重启时重复写入。
    """
    try:
        embedder = _build_embedder()
        lancedb = LanceDb(
            uri=cfg.storage.lancedb_uri,
            table_name=cfg.storage.lancedb_table,
            embedder=embedder,
        )
        knowledge = Knowledge(vector_db=lancedb)

        domain_refs = SKILLS_DIR / "domain_expert" / "references"
        if domain_refs.exists():
            for md_path in sorted(domain_refs.glob("*.md")):
                try:
                    knowledge.insert(
                        name=md_path.stem,
                        path=str(md_path),
                        skip_if_exists=True,
                    )
                    logger.debug("领域知识已灌入: %s", md_path.name)
                except Exception as exc:
                    logger.warning("知识灌入失败 %s: %s", md_path.name, exc)

        return knowledge
    except Exception as exc:
        logger.warning("Knowledge 初始化失败，跳过 RAG: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────
# System Prompt — 纯行为引导，不硬编码技能名
# 技能列表由 Skills.get_system_prompt_snippet() 自动注入 <skills_system> 块
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
你是家庭宽带体验感知优化专家。用户描述网络保障需求，你需要：
理解用户意图 → 补全用户画像 → 生成优化方案 → 约束校验 → 输出设备配置。

## 如何使用 Skills

通过 <skills_system> 中列出的元工具访问每个 Skill：
1. `get_skill_instructions(skill_name)` — 加载该 Skill 的完整使用指南（**调用前必须先加载**）
2. `get_skill_reference(skill_name, reference_path)` — 读取 Skill 的参考资料（schema、规则等）
3. `get_skill_script(skill_name, script_path, execute=True, args=[...])` — 执行 Skill 的 Python 脚本

**重要**：先调用 `get_skill_instructions` 理解 Skill 的输入输出格式，再执行脚本。

## 决策流程

**阶段1 — 理解意图**
- 加载意图解析 Skill，解析用户输入并校验意图完整性
- 如果意图不完整 → **必须暂停追问**，不要自行假设
- 追问用自然对话语气，每轮最多 2-3 个字段，最多追问 3 轮
- 本轮对话已获取的信息不要重复问

**阶段2 — 补全用户画像**
- 加载用户画像 Skill，查询缺失字段
- 能从意图推断的直接补全，关键字段追问，非关键字段用默认值

**阶段3 — 生成优化方案**
- 加载方案填充 Skill，基于意图+画像填充五大方案模板
- 填充后向用户展示修改摘要

**阶段4 — 约束校验（强制步骤，不可跳过）**
- 加载约束校验 Skill，执行性能、组网、冲突三类检查
- severity=error → 根据建议自动修正，重新校验
- severity=warning → 告知用户，等待确认
- 连续 3 次失败 → 声明需人工介入

**阶段5 — 输出设备配置**
- 加载配置转译 Skill，将方案转为设备下发格式
- 展示配置摘要、回退方案、注意事项

## 阶段间数据传递（节省 Token，必须遵守）

每个阶段脚本执行后，产出自动保存到 outputs/ 目录。
**后续阶段禁止将完整 JSON 内联在 args 中**——改用 `get_pipeline_file(stage)` 获取文件路径，
再通过 `--xxx-file <path>` 参数传给脚本，脚本直接从磁盘读取。

stage 名称对应关系：
- `intent`      ← extract.py 产出
- `profile`     ← query_profile.py 产出
- `plans`       ← generate.py 产出
- `constraint`  ← validate.py 产出

调用示例：
```
# 错误示范（浪费 3000+ token）：
get_skill_script("config_translator", "translate.py", execute=True,
                 args=['{"cei_perception": {...全量JSON...}}'])

# 正确方式（文件路径只有几十字符）：
get_pipeline_file("plans")          # → "outputs/abc123/plans.json"
get_skill_script("config_translator", "translate.py", execute=True,
                 args=["--plans-file", "outputs/abc123/plans.json"])
```

## 通用规则
- 单轮使用一个 Skill，通过对话历史追踪已完成的步骤
- Skill 返回错误时主动向用户说明，不猜测
- 如需领域知识（CEI 指标、设备能力、术语），使用 knowledge 检索
- 用户意图明确且参数完整时，可跳过追问直接执行
"""


# ─────────────────────────────────────────────────────────────
# 管道文件工具 — 供模型获取上一阶段产出路径，避免内联 JSON
# ─────────────────────────────────────────────────────────────

def get_pipeline_file(stage: str) -> str:
    """获取本会话某阶段产出文件的路径。

    stage 可选值：intent / profile / plans / constraint / configs

    在调用下一阶段脚本前，先调用此工具获取上一阶段产出路径，
    再以 --xxx-file <path> 参数传给脚本，脚本从磁盘读取，
    避免将完整 JSON 内联到 args 中浪费 token。

    Returns:
        文件路径字符串（如 "outputs/abc123/plans.json"）
        或包含 error 字段的 JSON 字符串（文件不存在时）
    """
    sid = get_current_session_id()
    if not sid:
        return '{"error": "当前会话无阶段产出，请先执行对应阶段脚本"}'
    path = Path(f"outputs/{sid}/{stage}.json")
    if not path.exists():
        return f'{{"error": "文件不存在: {path}，请先执行上一阶段脚本"}}'
    return str(path)


# ─────────────────────────────────────────────────────────────
# Agent 构建
# ─────────────────────────────────────────────────────────────

def _build_model(llm: LLMConfig):
    """按 provider 字段选择 Agno 模型类

    provider=openai（默认）: OpenAIChat — 支持所有 OpenAI 兼容接口
      包括 OpenAI / DeepSeek / 本地 vLLM / 其他兼容服务
    provider=anthropic: Claude — Agno 原生 Anthropic 集成
      需要安装 `pip install anthropic`
    """
    if llm.provider == "anthropic":
        from agno.models.anthropic.claude import Claude
        return Claude(
            id=llm.model,
            api_key=llm.api_key,
        )
    # 默认：openai 兼容
    # 覆盖 role_map：Agno 默认把 system 映射为 developer（跟 OpenAI o1 格式走），
    # 但大多数 OpenAI 兼容接口（qwen、本地模型等）只支持标准的 system role，需显式还原。
    return OpenAIChat(
        id=llm.model,
        api_key=llm.api_key,
        base_url=llm.base_url,
        role_map={
            "system": "system",
            "user": "user",
            "assistant": "assistant",
            "tool": "tool",
            "model": "assistant",
        },
    )


def build_agent() -> Agent:
    """构建并返回 Agent 实例"""
    skills = discover_skills(SKILLS_DIR)
    knowledge = build_knowledge()
    model = _build_model(cfg.llm)

    return Agent(
        model=model,
        skills=skills,
        tools=[get_pipeline_file],
        knowledge=knowledge,
        instructions=SYSTEM_PROMPT,

        # 会话对话历史
        add_history_to_context=True,
        num_history_runs=cfg.pipeline.num_history_runs,

        # 工具调用上限（防止死循环，对应设计文档的 max_turns 概念）
        tool_call_limit=cfg.pipeline.max_turns,

        # User Memory（跨会话记忆）— P1，用户系统就绪后启用
        # enable_user_memories=True,

        # 会话持久化（SQLite）
        db=SqliteDb(db_file=cfg.storage.sqlite_db_path),

        tool_hooks=[output_sink_hook],
        pre_hooks=[PromptInjectionGuardrail()],
        reasoning=cfg.llm.reasoning,
        markdown=True,
        debug_mode=cfg.pipeline.debug_mode,
    )


# ─────────────────────────────────────────────────────────────
# 模块级惰性单例（避免 import 时立即触发 LLM/DB 初始化）
# ─────────────────────────────────────────────────────────────

_agent: Agent | None = None


def get_agent() -> Agent:
    """惰性初始化 Agent 单例，首次调用时构建"""
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent
