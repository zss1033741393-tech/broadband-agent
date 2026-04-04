"""IntentAgent — 目标解析 + 追问 + 用户画像（阶段1）"""
from __future__ import annotations

from agno.agent import Agent
from agno.skills import LocalSkills, Skills

from .tools import get_pipeline_file, SKILLS_DIR

INTENT_PROMPT = """\
你是意图解析与用户画像专家。处理流程：
1. 使用 intent_parser Skill 解析用户意图，提取结构化 IntentGoal 字段
   需要的字段：user_type（用户类型）、scenario（场景）、guarantee_target（保障对象）
2. 使用 user_profiler Skill 补全用户画像（应用历史、设备信息等）
3. 意图不完整（needs_clarification=true）时生成追问话术返回（每轮≤3字段，最多3轮）
4. complete=true 且画像完整后返回结构化结果，不执行其他操作
"""


def build_intent_agent(model, num_history_runs: int, debug_mode: bool) -> Agent:
    skills = Skills(loaders=[
        LocalSkills(path=str(SKILLS_DIR / "intent_parser"), validate=False),
        LocalSkills(path=str(SKILLS_DIR / "user_profiler"), validate=False),
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
