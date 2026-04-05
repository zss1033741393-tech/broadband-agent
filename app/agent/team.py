"""OrchestratorTeam — 主控（Agno Team，TeamMode.coordinate）

协调 4 个专家子 Agent 完成完整的宽带优化流程：
  IntentAgent      → 目标解析 + 追问 + 用户画像
  PlanAgent        → 五大方案生成
  ConstraintAgent  → 约束校验（必须执行）
  ConfigAgent      → 配置转译

领域知识（domain_expert Skill）已下沉至各子 Agent，
主控仅负责流程调度，不挂载 Knowledge RAG。
"""
from __future__ import annotations

import logging

from agno.db.sqlite import SqliteDb
from agno.guardrails import PromptInjectionGuardrail
from agno.models.openai import OpenAIChat
from agno.team import Team, TeamMode

from app.config import LLMConfig, load_config
from app.outputs.sink import output_sink_hook

from .intent_agent import build_intent_agent
from .plan_agent import build_plan_agent
from .constraint_agent import build_constraint_agent
from .config_agent import build_config_agent

logger = logging.getLogger("agent.team")

cfg = load_config()

ORCHESTRATOR_PROMPT = """\
你是家庭宽带 CEI 体验感知优化主控。按如下流程将任务委托给专家子 Agent：

1. IntentAgent — 解析用户意图 + 补全画像
   若追问未完成 → 将追问话术原样转达用户，等待回复后继续

2. PlanAgent — 生成五大优化方案（基于意图和画像）

3. ConstraintAgent — 校验约束（必须执行，不可跳过）
   conflicts → 将 suggestions 传给 PlanAgent 重新生成（最多3轮）
   warnings → 告知用户，等待确认后继续

4. ConfigAgent — 生成 4 类设备配置，展示摘要

各阶段完成后立即衔接，不等待用户中间确认（除非需要追问或 warning 确认）。
"""


def _build_model(llm: LLMConfig, model_id: str | None = None):
    """按 provider 选择模型；model_id 非 None 时覆盖 llm.model"""
    actual_model = model_id or llm.model
    if llm.provider == "anthropic":
        from agno.models.anthropic.claude import Claude
        return Claude(id=actual_model, api_key=llm.api_key)
    return OpenAIChat(
        id=actual_model,
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


def build_team() -> Team:
    """构建并返回 OrchestratorTeam 实例"""
    agents_cfg = cfg.pipeline.agents
    debug_mode = cfg.pipeline.debug_mode

    intent_agent = build_intent_agent(
        model=_build_model(cfg.llm, agents_cfg.intent.model),
        num_history_runs=agents_cfg.intent.num_history_runs,
        debug_mode=debug_mode,
    )
    plan_agent = build_plan_agent(
        model=_build_model(cfg.llm, agents_cfg.plan.model),
        num_history_runs=agents_cfg.plan.num_history_runs,
        debug_mode=debug_mode,
    )
    constraint_agent = build_constraint_agent(
        model=_build_model(cfg.llm, agents_cfg.constraint.model),
        num_history_runs=agents_cfg.constraint.num_history_runs,
        debug_mode=debug_mode,
    )
    config_agent = build_config_agent(
        model=_build_model(cfg.llm, agents_cfg.config.model),
        num_history_runs=agents_cfg.config.num_history_runs,
        debug_mode=debug_mode,
    )

    return Team(
        name="家宽CEI体验优化团队",
        members=[intent_agent, plan_agent, constraint_agent, config_agent],
        mode=TeamMode.coordinate,
        model=_build_model(cfg.llm),
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
