import asyncio
import json
import time
from typing import Optional

from agno.agent import Agent
from agno.models.openai import OpenAILike

from app.config import LLMConfig, load_llm_config, load_pipeline_config, load_skill
from app.logger import get_logger, log_step, record_llm_trace
from app.models.intent import IntentGoal
from app.models.plan import FilledPlan, PlanFillResult
from app.tools.template_tools import load_template

logger = get_logger("Stage2", "PlanFiller")

TEMPLATE_NAMES = [
    "cei_perception_plan",
    "fault_diagnosis_plan",
    "remote_closure_plan",
    "dynamic_optimization_plan",
    "manual_fallback_plan",
]

_INSTRUCTIONS = (
    load_skill("stage2", "plan_filling_skill")
    + "\n\n"
    + load_skill("stage2", "domain_knowledge_skill")
)


def _build_agent(cfg: LLMConfig) -> Agent:
    """构建 Stage2 PlanFiller Agent"""
    model = OpenAILike(
        id=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    return Agent(name="PlanFiller", model=model, instructions=_INSTRUCTIONS)


async def _fill_single_template(
    template_name: str,
    intent_goal: IntentGoal,
    cfg: LLMConfig,
    session_id: str,
    retry_hint: str = "",
) -> FilledPlan:
    """填充单个模板，并记录该次 LLM 请求轨迹

    Args:
        template_name: 模板名称
        intent_goal: 用户意图目标体
        cfg: 当前 Stage LLM 配置
        session_id: 会话 ID（用于轨迹记录）
        retry_hint: 约束校验失败时的回退调整指令

    Returns:
        FilledPlan
    """
    with log_step(logger, f"{template_name} 模板填充"):
        template = load_template(template_name)

        prompt_parts = [
            f"意图目标：\n{intent_goal.model_dump_json(indent=2)}",
            f"待填充模板（{template_name}）：\n{json.dumps(template, ensure_ascii=False, indent=2)}",
        ]
        if retry_hint:
            prompt_parts.append(f"上次约束校验失败，请按以下要求调整：\n{retry_hint}")
        prompt_parts.append(
            "请根据意图目标决定哪些参数需要修改，输出填充后的方案 JSON 和 changed_fields 列表。"
            "格式：{\"template_name\": \"...\", \"filled_plan\": {...}, \"changed_fields\": [...]}"
        )
        prompt = "\n\n".join(prompt_parts)

        agent = _build_agent(cfg)

        t0 = time.perf_counter()
        response = await agent.arun(prompt)
        latency_ms = (time.perf_counter() - t0) * 1000

        # 记录 LLM 请求级轨迹
        if session_id:
            await record_llm_trace(
                session_id=session_id,
                stage="Stage2",
                component=f"PlanFiller/{template_name}",
                llm_cfg=cfg,
                response=response,
                latency_ms=latency_ms,
            )

        content = str(response.content)
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            data = json.loads(content[start:end])
            return FilledPlan(
                template_name=template_name,
                filled_plan=data.get("filled_plan", template),
                changed_fields=data.get("changed_fields", []),
            )
        except Exception:
            logger.warning(f"{template_name} 解析失败，使用原始模板")
            return FilledPlan(template_name=template_name, filled_plan=template)


async def fill_all_plans(
    intent_goal: IntentGoal,
    retry_hint: str = "",
    retry_count: int = 0,
    session_id: str = "",
) -> PlanFillResult:
    """Stage2：基于意图目标填充五大方案模板

    Args:
        intent_goal: 用户意图目标体
        retry_hint: 约束校验失败时的回退调整指令
        retry_count: 当前重试次数
        session_id: 会话 ID（用于轨迹记录）

    Returns:
        PlanFillResult（包含 5 个填充后方案）
    """
    pipeline_cfg = load_pipeline_config()
    cfg = load_llm_config("stage2_plan")

    with log_step(logger, f"全部模板填充（retry={retry_count}）"):
        if pipeline_cfg.stage2_parallel:
            tasks = [
                _fill_single_template(name, intent_goal, cfg, session_id, retry_hint)
                for name in TEMPLATE_NAMES
            ]
            plans = list(await asyncio.gather(*tasks))
        else:
            plans = []
            for name in TEMPLATE_NAMES:
                plan = await _fill_single_template(name, intent_goal, cfg, session_id, retry_hint)
                plans.append(plan)

    logger.info(f"方案填充完成 | 模板数={len(plans)} | retry_count={retry_count}")
    return PlanFillResult(
        intent_goal_snapshot=intent_goal.model_dump(),
        plans=plans,
        retry_count=retry_count,
    )
