import json
from typing import Optional

from agno.agent import Agent
from agno.models.openai import OpenAILike

from app.config import load_llm_config, load_skill
from app.logger import get_logger, log_step
from app.models.intent import IntentGoal
from app.tools.profile_tools import load_user_profile, query_app_history, query_network_kpi

logger = get_logger("Stage1", "IntentParser")

# 加载 Stage1 Skills（渐进式加载，仅加载本阶段所需）
_INSTRUCTIONS = (
    load_skill("stage1", "intent_parsing_skill")
    + "\n\n"
    + load_skill("stage1", "user_profile_skill")
)


def _build_agent() -> Agent:
    """构建 Stage1 IntentParser Agent"""
    cfg = load_llm_config("stage1_intent")
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
) -> IntentGoal:
    """Stage1：解析用户意图，缺失信息追问

    Args:
        user_input: 用户自然语言输入
        user_id: 用户 ID，用于加载历史画像
        history: 对话历史（追问补充场景）

    Returns:
        结构化意图目标体 IntentGoal
    """
    with log_step(logger, "意图解析"):
        # 加载用户历史数据
        profile_data = await load_user_profile(user_id)
        app_history = await query_app_history(user_id)
        network_kpi = await query_network_kpi(user_id)

        # 构建 prompt，注入历史数据
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

        agent = _build_agent()
        response = await agent.arun(prompt)

        if isinstance(response.content, IntentGoal):
            intent = response.content
        else:
            # fallback：尝试解析 JSON 字符串
            intent = IntentGoal.model_validate_json(str(response.content))

        logger.info(
            f"意图解析完成 | user_type={intent.user_type} "
            f"| need_followup={intent.need_followup} "
            f"| missing_fields={intent.missing_fields}"
        )
        return intent
