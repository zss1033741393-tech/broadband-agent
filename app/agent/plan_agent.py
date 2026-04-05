"""PlanAgent — 五大优化方案生成（阶段2）"""
from __future__ import annotations

from agno.agent import Agent
from agno.skills import LocalSkills, Skills

from .tools import get_pipeline_file, SKILLS_DIR

PLAN_PROMPT = """\
你是方案生成专家。处理流程：
1. 通过 get_pipeline_file("intent") 获取意图文件路径
2. 使用 plan_generator Skill 的 generate.py，传入 --intent-file <path>，填充五大方案模板：
   体验感知方案 / 故障诊断方案 / 远程闭环处置方案 / 智能动态优化方案 / 人工兜底方案
3. 生成完成后返回方案摘要（changes 列表），不执行其他操作
4. 若收到约束建议（suggestions），按建议调整参数后重新生成，无需等待用户确认
"""


def build_plan_agent(model, num_history_runs: int, debug_mode: bool) -> Agent:
    skills = Skills(loaders=[
        LocalSkills(path=str(SKILLS_DIR / "plan_generator"), validate=False),
        LocalSkills(path=str(SKILLS_DIR / "domain_expert"), validate=False),
    ])
    return Agent(
        name="PlanAgent",
        role="方案生成",
        model=model,
        skills=skills,
        tools=[get_pipeline_file],
        instructions=PLAN_PROMPT,
        add_history_to_context=True,
        num_history_runs=num_history_runs,
        markdown=True,
        debug_mode=debug_mode,
    )
