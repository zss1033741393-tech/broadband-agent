"""IntentAgent — 意图解析 + 画像补全（阶段1）"""
from __future__ import annotations

from agno.agent import Agent
from agno.skills import LocalSkills, Skills

from app.outputs.sink import output_sink_hook
from .tools import get_pipeline_file, analyze_intent, SKILLS_DIR

INTENT_PROMPT = """\
你是意图解析与用户画像专家。处理流程：
1. 从用户输入中提取意图字段（user_type / scenario / guarantee_target / guarantee_period 等）
2. 调用 analyze_intent(intent_goal={...}) 执行画像推断补全 + 完整性校验
3. 意图不完整（complete=false）时用返回的 followup 追问用户（每轮≤3字段，最多3轮）
4. 收到用户补充信息后，将新信息合并到 intent_goal 中再次调用 analyze_intent
5. complete=true 后返回结构化结果，不执行其他操作
6. 需要理解专业术语时，可查阅 domain_expert 的 glossary.md

严禁事项：
- 禁止跳过 analyze_intent 工具自行编造意图或画像数据
- 禁止在未调用工具的情况下虚构 JSON 结果
- 如果工具返回错误，必须停止流程并将错误信息反馈给用户
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
        tools=[get_pipeline_file, analyze_intent],
        instructions=INTENT_PROMPT,
        add_history_to_context=True,
        num_history_runs=num_history_runs,
        tool_hooks=[output_sink_hook],
        markdown=True,
        debug_mode=debug_mode,
    )
