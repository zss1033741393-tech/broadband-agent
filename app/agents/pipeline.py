import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.agents.config_agent import translate_config
from app.agents.constraint_agent import check_constraints
from app.agents.intent_agent import parse_intent
from app.agents.plan_agent import fill_all_plans
from app.config import load_pipeline_config
from app.db.crud import (
    save_intent_goal,
    save_pipeline_output,
    save_plan_result,
    save_session,
)
from app.logger import get_logger, log_step
from app.models.config import PipelineOutput
from app.models.intent import IntentGoal
from app.models.plan import PlanFillResult

logger = get_logger("Pipeline", "Orchestrator")


@dataclass
class PipelineState:
    """Pipeline 运行状态，贯穿全程"""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "anonymous"
    intent_goal: Optional[IntentGoal] = None
    plan_result: Optional[PlanFillResult] = None
    output: Optional[PipelineOutput] = None
    status: str = "init"           # init / waiting_followup / running / done / error
    followup_question: str = ""    # 追问内容（status=waiting_followup 时非空）
    error_message: str = ""


async def run_pipeline(
    user_input: str,
    user_id: str = "anonymous",
    session_id: Optional[str] = None,
    dialog_history: Optional[list[dict]] = None,
) -> PipelineState:
    """运行完整 Pipeline（Stage1 → 2 → 3 → 4）

    Args:
        user_input: 用户自然语言输入（或追问回复）
        user_id: 用户 ID
        session_id: 会话 ID（续接对话时传入）
        dialog_history: 对话历史（追问场景）

    Returns:
        PipelineState（status=done 表示完成，waiting_followup 表示需继续追问）
    """
    cfg = load_pipeline_config()
    state = PipelineState(
        session_id=session_id or str(uuid.uuid4()),
        user_id=user_id,
    )

    try:
        # 持久化会话
        await save_session(state.session_id, user_id)
        state.status = "running"

        # ─── Stage 1：意图解析 ───
        with log_step(logger, "Stage1 意图解析"):
            intent = await parse_intent(user_input, user_id, dialog_history)
            state.intent_goal = intent
            await save_intent_goal(state.session_id, intent.model_dump())

        # 若需要追问，暂停 Pipeline 等待用户补充
        if intent.need_followup:
            state.status = "waiting_followup"
            state.followup_question = intent.followup_question
            logger.info(f"需要追问 | question={intent.followup_question}")
            return state

        # ─── Stage 2 + 3：方案生成 + 约束校验（带回退重试）───
        retry_hint = ""
        plan_result: Optional[PlanFillResult] = None

        for attempt in range(cfg.max_retry_on_constraint_fail + 1):
            # Stage 2：方案填充
            with log_step(logger, f"Stage2 方案生成（attempt={attempt}）"):
                plan_result = await fill_all_plans(intent, retry_hint, attempt)
                await save_plan_result(state.session_id, plan_result.model_dump(), attempt)

            if not cfg.enable_stage3:
                logger.info("Stage3 已禁用，跳过约束校验")
                break

            # Stage 3：约束校验
            with log_step(logger, f"Stage3 约束校验（attempt={attempt}）"):
                check_result = await check_constraints(plan_result)

            if check_result.passed:
                logger.info(f"约束校验通过，共尝试 {attempt + 1} 次")
                break

            # 校验失败且未超出最大重试次数
            if attempt < cfg.max_retry_on_constraint_fail:
                retry_hint = check_result.retry_hint
                logger.warning(f"约束校验失败，回退 Stage2 重试 | attempt={attempt + 1}")
            else:
                # 超出重试限制，记录警告并继续（人工兜底）
                logger.error(
                    f"约束校验失败已达最大重试次数 {cfg.max_retry_on_constraint_fail}，"
                    "继续输出（需人工审核）"
                )
                break

        state.plan_result = plan_result

        # ─── Stage 4：配置输出 ───
        if cfg.enable_stage4 and plan_result:
            with log_step(logger, "Stage4 配置转译"):
                output = await translate_config(plan_result, state.session_id)
                state.output = output
                await save_pipeline_output(
                    state.session_id,
                    output.model_dump(),
                    output.output_files,
                )
        else:
            logger.info("Stage4 已禁用，跳过配置转译")

        state.status = "done"
        logger.info(f"Pipeline 完成 | session_id={state.session_id}")

    except Exception as e:
        state.status = "error"
        state.error_message = str(e)
        logger.error(f"Pipeline 异常 | error={e}")
        raise

    return state
