"""IntentAgent — 意图解析 + 画像补全（阶段1）"""
from __future__ import annotations

from agno.agent import Agent
from agno.skills import LocalSkills, Skills

from .tools import get_pipeline_file, SKILLS_DIR

INTENT_PROMPT = """\
你是意图解析与用户画像专家。处理流程：
1. 使用 intent_profiler Skill 一次性完成：意图提取 + 画像推断补全 + 完整性校验
2. 意图不完整（complete=false）时用 followup 追问用户（每轮≤3字段，最多3轮）
3. complete=true 后返回结构化结果，不执行其他操作
4. 需要理解专业术语时，可查阅 domain_expert 的 glossary.md
"""


def build_intent_agent(model, num_history_runs: int, debug_mode: bool) -> Agent:
    skills = Skills(loaders=[
        LocalSkills(path=str(SKILLS_DIR / "intent_profiler"), validate=False),
        LocalSkills(path=str(SKILLS_DIR / "domain_expert"), validate=False),
    ])
    return Agent(
        name="IntentAgent",
        role="意图解析与用户画像",
        model=model,
        skills=skills,
        tools=[get_pipeline_file],
        instructions=INTENT_PROMPT,
        add_history_to_context=True,
        num_history_runs=num_history_runs,
        markdown=True,
        debug_mode=debug_mode,
    )
