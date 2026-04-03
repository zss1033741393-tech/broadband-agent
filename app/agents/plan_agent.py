import asyncio
import json
from typing import Optional

from agno.agent import Agent
from agno.models.openai import OpenAILike

from app.config import load_llm_config, load_pipeline_config, load_skill
from app.logger import get_logger, log_step
from app.models.intent import IntentGoal
from app.models.plan import FilledPlan, PlanFillResult
from app.tools.template_tools import load_template

logger = get_logger("Stage2", "PlanFiller")

# 五大方案模板名
TEMPLATE_NAMES = [
    "cei_perception_plan",
    "fault_diagnosis_plan",
    "remote_closure_plan",
    "dynamic_optimization_plan",
    "manual_fallback_plan",
]

# 加载 Stage2 Skills
_INSTRUCTIONS = (
    load_skill("stage2", "plan_filling_skill")
    + "\n\n"
    + load_skill("stage2", "domain_knowledge_skill")
)


def _build_agent() -> Agent:
    """构建 Stage2 PlanFiller Agent"""
    cfg = load_llm_config("stage2_plan")
    model = OpenAILike(
        id=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    return Agent(
        name="PlanFiller",
        model=model,
        instructions=_INSTRUCTIONS,
    )


async def _fill_single_template(
    template_name: str,
    intent_goal: IntentGoal,
    retry_hint: str = "",
) -> FilledPlan:
    """填充单个模板

    Args:
        template_name: 模板名称
        intent_goal: 用户意图目标体
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

        agent = _build_agent()
        response = await agent.arun(prompt)

        # 解析响应
        content = str(response.content)
        try:
            # 尝试从响应中提取 JSON
            start = content.find("{")
            end = content.rfind("}") + 1
            data = json.loads(content[start:end])
            return FilledPlan(
                template_name=template_name,
                filled_plan=data.get("filled_plan", template),
                changed_fields=data.get("changed_fields", []),
            )
        except Exception:
            # fallback：返回未修改的模板
            logger.warning(f"{template_name} 解析失败，使用原始模板")
            return FilledPlan(template_name=template_name, filled_plan=template)


async def fill_all_plans(
    intent_goal: IntentGoal,
    retry_hint: str = "",
    retry_count: int = 0,
) -> PlanFillResult:
    """Stage2：基于意图目标填充五大方案模板

    Args:
        intent_goal: 用户意图目标体
        retry_hint: 约束校验失败时的回退调整指令
        retry_count: 当前重试次数

    Returns:
        PlanFillResult（包含 5 个填充后方案）
    """
    pipeline_cfg = load_pipeline_config()

    with log_step(logger, f"全部模板填充（retry={retry_count}）"):
        if pipeline_cfg.stage2_parallel:
            # 并行填充（快，适合生产环境）
            tasks = [
                _fill_single_template(name, intent_goal, retry_hint)
                for name in TEMPLATE_NAMES
            ]
            plans = list(await asyncio.gather(*tasks))
        else:
            # 串行填充（省资源，适合调试）
            plans = []
            for name in TEMPLATE_NAMES:
                plan = await _fill_single_template(name, intent_goal, retry_hint)
                plans.append(plan)

    logger.info(f"方案填充完成 | 模板数={len(plans)} | retry_count={retry_count}")
    return PlanFillResult(
        intent_goal_snapshot=intent_goal.model_dump(),
        plans=plans,
        retry_count=retry_count,
    )
