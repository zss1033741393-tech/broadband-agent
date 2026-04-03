"""Agno Agent 定义 + system prompt — Agent 自主决策，不做硬编排"""
import logging
from typing import Any

from openai import AsyncOpenAI

from app.agent.skill_loader import build_skills_summary, discover_skills
from app.agent.tracer import AgentTracer
from app.config import get_model_config

logger = logging.getLogger("agent")

SYSTEM_PROMPT_TEMPLATE = """# 你是家宽体验感知优化 Agent

你是一个智能配置生成助手。用户会描述他们的保障需求，你需要理解意图、生成优化方案、校验约束、输出设备配置。

## 工作指导（建议但不强制的顺序）

1. 先理解用户意图，如果信息不完整就追问
2. 收集到足够信息后，填充对应的方案模板
3. 填充完成后进行约束校验
4. 校验通过后转译为设备配置

你可以根据实际情况灵活调整：
- 如果用户直接给出了完整参数，可以跳过追问
- 如果某个方案不需要修改，保持默认即可
- 如果校验发现冲突，回头调整方案参数
- 如果用户中途改了需求，重新理解意图

## 可用 Skills

以下是你可以调用的能力包，根据当前任务自行选择：

{skills_summary}

## 回复格式

每次回复时，请先以 <thinking> 标签输出你的思考过程（选择了哪个 Skill、为什么），
再给出面向用户的回复。

示例：
<thinking>
用户描述了直播场景，信息还不够完整，需要了解敏感度和具体应用。
选择 intent_parsing Skill 进行意图解析。
</thinking>

请问您对直播卡顿的敏感程度如何？主要使用什么推流应用？
"""


class BroadbandAgent:
    """家宽体验感知优化 Agent — 基于 OpenAI API 兼容格式"""

    def __init__(self) -> None:
        self.skills = discover_skills()
        skills_summary = build_skills_summary(self.skills)
        self.system_prompt = SYSTEM_PROMPT_TEMPLATE.format(skills_summary=skills_summary)

        model_cfg = get_model_config("main")
        self.client = AsyncOpenAI(
            api_key=model_cfg.get("api_key", "sk-xxx"),
            base_url=model_cfg.get("base_url", "https://api.openai.com/v1"),
        )
        self.model = model_cfg.get("model", "gpt-4o")
        self.temperature = model_cfg.get("temperature", 0.7)
        self.max_tokens = model_cfg.get("max_tokens", 4096)

        logger.info(
            "BroadbandAgent 初始化完成 | model=%s | skills=%d",
            self.model,
            len(self.skills),
        )

    async def run(
        self,
        user_message: str,
        history: list[dict[str, str]],
        tracer: AgentTracer,
    ) -> dict[str, Any]:
        """
        处理用户消息，返回 Agent 回复。

        Returns:
            dict with keys: content, thinking, skill_used
        """
        tracer.log("user_input", content=user_message)

        # 构建消息历史
        messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        for msg in history:
            messages.append(msg)
        messages.append({"role": "user", "content": user_message})

        logger.debug(
            "[Agent] LLM 调用 | model=%s | history_turns=%d",
            self.model,
            len(history),
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        raw_content = response.choices[0].message.content or ""

        # 解析 <thinking> 标签
        thinking = ""
        content = raw_content
        if "<thinking>" in raw_content and "</thinking>" in raw_content:
            start = raw_content.index("<thinking>") + len("<thinking>")
            end = raw_content.index("</thinking>")
            thinking = raw_content[start:end].strip()
            content = raw_content[end + len("</thinking>"):].strip()

        # 从思考内容中推断 Skill 使用情况
        skill_used = self._infer_skill(thinking + content)

        tracer.log(
            "agent_thinking",
            content=thinking,
            skill_selected=skill_used,
        )
        tracer.log("agent_output", content=content, skill_used=skill_used)

        logger.info(
            "[Agent] 回复生成完成 | skill=%s | tokens=%d",
            skill_used,
            response.usage.total_tokens if response.usage else 0,
        )

        return {"content": content, "thinking": thinking, "skill_used": skill_used}

    def _infer_skill(self, text: str) -> str:
        """从文本中推断使用了哪个 Skill（简单关键词匹配）"""
        skill_keywords = {
            "intent_parsing": ["意图", "理解", "追问", "intent"],
            "user_profile": ["画像", "历史", "用户信息", "profile"],
            "plan_filling": ["方案", "模板", "填充", "plan"],
            "constraint_check": ["约束", "校验", "冲突", "constraint"],
            "config_translation": ["配置", "转译", "NL2JSON", "config"],
            "domain_knowledge": ["术语", "领域", "CEI", "domain"],
        }
        text_lower = text.lower()
        for skill_name, keywords in skill_keywords.items():
            if any(kw in text_lower or kw in text for kw in keywords):
                return skill_name
        return ""
