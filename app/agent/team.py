"""OrchestratorTeam — 主控（Agno Team，TeamMode.coordinate）

协调 4 个专家子 Agent 完成完整的宽带优化流程：
  IntentAgent  → 目标解析 + 追问 + 用户画像
  PlanAgent    → 五大方案生成
  ConstraintAgent → 约束校验（可选）
  ConfigAgent  → 配置转译
"""
from __future__ import annotations

import logging
from pathlib import Path

from agno.db.sqlite import SqliteDb
from agno.guardrails import PromptInjectionGuardrail
from agno.knowledge import Knowledge
from agno.models.openai import OpenAIChat
from agno.team import Team, TeamMode
from agno.vectordb.lancedb import LanceDb

from app.config import LLMConfig, load_config
from app.outputs.sink import output_sink_hook

from .intent_agent import build_intent_agent
from .plan_agent import build_plan_agent
from .constraint_agent import build_constraint_agent
from .config_agent import build_config_agent
from .tools import SKILLS_DIR

logger = logging.getLogger("agent.team")

cfg = load_config()

ORCHESTRATOR_PROMPT = """\
你是家庭宽带体验感知优化主控。按如下流程将任务委托给专家子 Agent：

1. IntentAgent — 解析用户意图 + 补全画像
   若追问未完成 → 将追问话术原样转达用户，等待回复后继续

2. PlanAgent — 生成五大优化方案（基于意图和画像）

3. ConstraintAgent — 校验约束（必须执行，不可跳过）
   conflicts → 将 suggestions 传给 PlanAgent 重新生成（最多3轮）
   warnings → 告知用户，等待确认后继续

4. ConfigAgent — 生成 4 类设备配置，展示摘要

各阶段完成后立即衔接，不等待用户中间确认（除非需要追问或 warning 确认）。
"""


def _build_model(llm: LLMConfig):
    """按 provider 选择模型"""
    if llm.provider == "anthropic":
        from agno.models.anthropic.claude import Claude
        return Claude(id=llm.model, api_key=llm.api_key)
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


def build_knowledge() -> Knowledge | None:
    """构建 LanceDB Knowledge，灌入 domain_expert/references/ 中的文本类文档"""
    try:
        if cfg.llm.provider == "anthropic":
            from agno.knowledge.embedder.fastembed import FastEmbedEmbedder
            embedder = FastEmbedEmbedder()
        else:
            from agno.knowledge.embedder.openai_like import OpenAILikeEmbedder
            embedder = OpenAILikeEmbedder(
                id="text-embedding-3-small",
                api_key=cfg.llm.api_key,
                base_url=cfg.llm.base_url,
            )
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
                    knowledge.insert(name=md_path.stem, path=str(md_path), skip_if_exists=True)
                    logger.debug("领域知识已灌入: %s", md_path.name)
                except Exception as exc:
                    logger.warning("知识灌入失败 %s: %s", md_path.name, exc)
        return knowledge
    except Exception as exc:
        logger.warning("Knowledge 初始化失败，跳过 RAG: %s", exc)
        return None


def build_team() -> Team:
    """构建并返回 OrchestratorTeam 实例"""
    model = _build_model(cfg.llm)
    knowledge = build_knowledge()

    intent_agent = build_intent_agent(model)
    plan_agent = build_plan_agent(model)
    constraint_agent = build_constraint_agent(model)
    config_agent = build_config_agent(model)

    return Team(
        name="宽带优化团队",
        members=[intent_agent, plan_agent, constraint_agent, config_agent],
        mode=TeamMode.coordinate,
        model=model,
        knowledge=knowledge,
        instructions=ORCHESTRATOR_PROMPT,
        add_history_to_context=True,
        num_history_runs=cfg.pipeline.num_history_runs,
        share_member_interactions=True,
        stream_member_events=True,
        tool_hooks=[output_sink_hook],
        pre_hooks=[PromptInjectionGuardrail()],
        tool_call_limit=cfg.pipeline.max_turns,
        db=SqliteDb(db_file=cfg.storage.sqlite_db_path),
        reasoning=cfg.llm.reasoning,
        markdown=True,
        debug_mode=cfg.pipeline.debug_mode,
    )


# ─────────────────────────────────────────────────────────────
# 模块级惰性单例
# ─────────────────────────────────────────────────────────────

_team: Team | None = None


def get_team() -> Team:
    """惰性初始化 Team 单例，首次调用时构建"""
    global _team
    if _team is None:
        _team = build_team()
    return _team
