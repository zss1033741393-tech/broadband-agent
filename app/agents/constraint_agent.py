import json
import time

from agno.agent import Agent
from agno.models.openai import OpenAILike

from app.config import LLMConfig, load_llm_config, load_skill
from app.logger import get_logger, log_step, record_llm_trace
from app.models.plan import ConstraintCheckResult, ConstraintViolation, PlanFillResult
from app.tools.constraint_tools import check_conflict, check_network_topology, check_performance

logger = get_logger("Stage3", "ConstraintChecker")

_INSTRUCTIONS = load_skill("stage3", "constraint_check_skill")


def _build_agent(cfg: LLMConfig) -> Agent:
    """构建 Stage3 ConstraintChecker Agent"""
    model = OpenAILike(
        id=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    return Agent(name="ConstraintChecker", model=model, instructions=_INSTRUCTIONS)


async def check_constraints(
    plan_result: PlanFillResult,
    session_id: str = "",
) -> ConstraintCheckResult:
    """Stage3：对五大方案执行约束校验

    Args:
        plan_result: Stage2 输出的方案填充结果
        session_id: 会话 ID（用于轨迹记录）

    Returns:
        ConstraintCheckResult（passed=True 则继续，False 则回退 Stage2）
    """
    with log_step(logger, "约束校验"):
        plans_dict: dict = {}
        for filled in plan_result.plans:
            plans_dict[filled.template_name] = filled.filled_plan

        all_violations: list[ConstraintViolation] = []

        # 1. 参数范围校验（纯代码规则，无 LLM）
        for result in (
            check_performance(plans_dict),
            check_network_topology(plans_dict),
            check_conflict(plans_dict),
        ):
            for v in result.get("violations", []):
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

        cfg = load_llm_config("stage3_constraint")
        agent = _build_agent(cfg)

        t0 = time.perf_counter()
        response = await agent.arun(prompt)
        latency_ms = (time.perf_counter() - t0) * 1000

        # 记录 LLM 请求级轨迹
        if session_id:
            await record_llm_trace(
                session_id=session_id,
                stage="Stage3",
                component="ConstraintChecker",
                llm_cfg=cfg,
                response=response,
                latency_ms=latency_ms,
            )

        retry_hint = str(response.content)

        logger.warning(
            f"约束校验失败 | violations={len(all_violations)} | retry_hint={retry_hint[:100]}"
        )
        return ConstraintCheckResult(
            passed=False,
            violations=all_violations,
            retry_hint=retry_hint,
        )
