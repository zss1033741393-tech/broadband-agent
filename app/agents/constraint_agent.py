import json

from agno.agent import Agent
from agno.models.openai import OpenAILike

from app.config import load_llm_config, load_skill
from app.logger import get_logger, log_step
from app.models.plan import ConstraintCheckResult, ConstraintViolation, PlanFillResult
from app.tools.constraint_tools import check_conflict, check_network_topology, check_performance

logger = get_logger("Stage3", "ConstraintChecker")

# 加载 Stage3 Skills
_INSTRUCTIONS = load_skill("stage3", "constraint_check_skill")


def _build_agent() -> Agent:
    """构建 Stage3 ConstraintChecker Agent"""
    cfg = load_llm_config("stage3_constraint")
    model = OpenAILike(
        id=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    return Agent(
        name="ConstraintChecker",
        model=model,
        instructions=_INSTRUCTIONS,
    )


async def check_constraints(plan_result: PlanFillResult) -> ConstraintCheckResult:
    """Stage3：对五大方案执行约束校验

    Args:
        plan_result: Stage2 输出的方案填充结果

    Returns:
        ConstraintCheckResult（passed=True 则继续，False 则回退 Stage2）
    """
    with log_step(logger, "约束校验"):
        # 将方案整理为 dict 格式，方便工具函数处理
        plans_dict: dict = {}
        for filled in plan_result.plans:
            plans_dict[filled.template_name] = filled.filled_plan

        all_violations: list[ConstraintViolation] = []

        # 1. 参数范围校验
        perf_result = check_performance(plans_dict)
        for v in perf_result.get("violations", []):
            all_violations.append(ConstraintViolation(**v))

        # 2. 组网逻辑校验
        topo_result = check_network_topology(plans_dict)
        for v in topo_result.get("violations", []):
            all_violations.append(ConstraintViolation(**v))

        # 3. 方案间冲突检测
        conflict_result = check_conflict(plans_dict)
        for v in conflict_result.get("violations", []):
            all_violations.append(ConstraintViolation(**v))

        if not all_violations:
            logger.info("约束校验通过")
            return ConstraintCheckResult(passed=True)

        # 有违规时，调用 LLM 生成回退指令
        violations_text = json.dumps(
            [v.model_dump() for v in all_violations], ensure_ascii=False, indent=2
        )
        prompt = (
            f"以下约束规则违规，请生成给 Stage2 的调整指令：\n{violations_text}\n\n"
            "请输出简洁的中文调整指令，说明需要修改哪些字段及建议值。"
        )
        agent = _build_agent()
        response = await agent.arun(prompt)
        retry_hint = str(response.content)

        logger.warning(
            f"约束校验失败 | violations={len(all_violations)} | retry_hint={retry_hint[:100]}"
        )
        return ConstraintCheckResult(
            passed=False,
            violations=all_violations,
            retry_hint=retry_hint,
        )
