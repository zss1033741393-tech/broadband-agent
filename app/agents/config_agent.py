import json
import time

from agno.agent import Agent
from agno.models.openai import OpenAILike

from app.config import LLMConfig, load_llm_config, load_skill
from app.logger import get_logger, log_step, record_llm_trace
from app.models.config import PipelineOutput
from app.models.plan import PlanFillResult
from app.tools.config_tools import export_config, translate_to_config, validate_config

logger = get_logger("Stage4", "ConfigTranslator")

_INSTRUCTIONS = load_skill("stage4", "config_translation_skill")


def _build_agent(cfg: LLMConfig) -> Agent:
    """构建 Stage4 ConfigTranslator Agent"""
    model = OpenAILike(
        id=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    return Agent(name="ConfigTranslator", model=model, instructions=_INSTRUCTIONS)


async def translate_config(
    plan_result: PlanFillResult,
    session_id: str,
) -> PipelineOutput:
    """Stage4：将校验通过的方案转译为设备可执行配置

    Args:
        plan_result: Stage2/3 通过校验的方案填充结果
        session_id: 会话 ID

    Returns:
        PipelineOutput（包含 4 类配置 + 导出文件路径）
    """
    with log_step(logger, "配置转译（NL2JSON）"):
        plans_dict: dict = {}
        for filled in plan_result.plans:
            plans_dict[filled.template_name] = filled.filled_plan

        # 用规则引擎做基础字段映射转译
        output = translate_to_config(plans_dict, session_id)

        # 调用 LLM 做复杂语义转译校验和补充（可选增强）
        cfg = load_llm_config("stage4_config")
        agent = _build_agent(cfg)

        verify_prompt = (
            f"请检查以下配置转译结果是否符合规范，如有问题指出并给出修正建议：\n"
            f"{json.dumps(output.model_dump(), ensure_ascii=False, indent=2)}"
        )

        t0 = time.perf_counter()
        response = await agent.arun(verify_prompt)
        latency_ms = (time.perf_counter() - t0) * 1000

        # 记录 LLM 请求级轨迹
        await record_llm_trace(
            session_id=session_id,
            stage="Stage4",
            component="ConfigTranslator",
            llm_cfg=cfg,
            response=response,
            latency_ms=latency_ms,
        )

        # 格式校验
        validation = validate_config(output)
        if not validation["passed"]:
            logger.warning(f"配置格式校验异常 | errors={validation['errors']}")
        else:
            logger.info("配置格式校验通过")

        # 导出配置文件
        output_files = export_config(output)
        output.output_files = output_files
        output.validation_passed = validation["passed"]

        logger.info(
            f"配置转译完成 | session_id={session_id} "
            f"| files={len(output_files)} | validation={validation['passed']}"
        )
        return output
