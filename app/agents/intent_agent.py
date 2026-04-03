import json
import time
from typing import Optional

from agno.agent import Agent
from agno.models.openai import OpenAILike

from app.config import LLMConfig, load_llm_config, load_skill
from app.logger import get_logger, log_step, record_llm_trace
from app.models.intent import IntentGoal
from app.tools.profile_tools import load_user_profile, query_app_history, query_network_kpi

logger = get_logger("Stage1", "IntentParser")

# 加载 Stage1 Skills（渐进式加载，仅加载本阶段所需）
_INSTRUCTIONS = (
    load_skill("stage1", "intent_parsing_skill")
    + "\n\n"
    + load_skill("stage1", "user_profile_skill")
)


def _build_agent(cfg: LLMConfig) -> Agent:
    """构建 Stage1 IntentParser Agent"""
    model = OpenAILike(
        id=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    return Agent(
        name="IntentParser",
        model=model,
        instructions=_INSTRUCTIONS,
        response_model=IntentGoal,
        structured_outputs=True,
    )


async def parse_intent(
    user_input: str,
    user_id: str = "anonymous",
    history: Optional[list[dict]] = None,
    session_id: str = "",
) -> IntentGoal:
    """Stage1：解析用户意图，缺失信息追问

    Args:
        user_input: 用户自然语言输入
        user_id: 用户 ID，用于加载历史画像
        history: 对话历史（追问补充场景）
        session_id: 会话 ID（用于轨迹记录）

    Returns:
        结构化意图目标体 IntentGoal
    """
    with log_step(logger, "意图解析"):
        # 加载用户历史数据
        profile_data = await load_user_profile(user_id)
        app_history = await query_app_history(user_id)
        network_kpi = await query_network_kpi(user_id)

        # 构建 prompt
        context_parts = [f"用户输入：{user_input}"]
        if profile_data.get("profile", {}).get("user_type"):
            context_parts.append(f"历史画像：{json.dumps(profile_data['profile'], ensure_ascii=False)}")
        if app_history:
            context_parts.append(f"应用行为历史：{json.dumps(app_history, ensure_ascii=False)}")
        if network_kpi:
            context_parts.append(f"网络KPI数据：{json.dumps(network_kpi, ensure_ascii=False)}")
        if history:
            context_parts.append(f"对话历史：{json.dumps(history, ensure_ascii=False)}")

        prompt = "\n\n".join(context_parts)
        prompt += "\n\n请解析用户意图并输出结构化 IntentGoal JSON。若有缺失必要信息，在 need_followup=true 中指定并写出追问内容。"

        cfg = load_llm_config("stage1_intent")
        agent = _build_agent(cfg)

        t0 = time.perf_counter()
        response = await agent.arun(prompt)
        latency_ms = (time.perf_counter() - t0) * 1000

        # 记录 LLM 请求级轨迹
        if session_id:
            await record_llm_trace(
                session_id=session_id,
                stage="Stage1",
                component="IntentParser",
                llm_cfg=cfg,
                response=response,
                latency_ms=latency_ms,
            )

        if isinstance(response.content, IntentGoal):
            intent = response.content
        else:
            intent = IntentGoal.model_validate_json(str(response.content))

        logger.info(
            f"意图解析完成 | user_type={intent.user_type} "
            f"| need_followup={intent.need_followup} "
            f"| missing_fields={intent.missing_fields}"
        )
        return intent
