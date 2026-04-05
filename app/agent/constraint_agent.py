"""ConstraintAgent — 约束校验（阶段3，可选）"""
from __future__ import annotations

from agno.agent import Agent
from agno.skills import LocalSkills, Skills

from app.outputs.sink import output_sink_hook
from .tools import get_pipeline_file, check_constraints, SKILLS_DIR

CONSTRAINT_PROMPT = """\
你是约束校验专家。处理流程：
1. 调用 check_constraints(get_pipeline_file("plans")) 执行约束校验
   - intent_goal 可省略，工具自动从 intent.json 读取
2. 返回校验结果：
   - passed=true → 返回"校验通过"
   - conflicts 非空 → 返回 suggestions 列表，主控将据此重新生成方案
   - warnings 非空 → 返回警告内容，由主控询问用户确认
3. 不执行校验以外的操作
"""


def build_constraint_agent(model, num_history_runs: int, debug_mode: bool) -> Agent:
    skills = Skills(loaders=[
        LocalSkills(path=str(SKILLS_DIR / "constraint_checker"), validate=False),
        LocalSkills(path=str(SKILLS_DIR / "domain_expert"), validate=False),
    ])
    return Agent(
        name="ConstraintAgent",
        role="约束校验",
        model=model,
        skills=skills,
        tools=[get_pipeline_file, check_constraints],
        instructions=CONSTRAINT_PROMPT,
        add_history_to_context=True,
        num_history_runs=num_history_runs,
        tool_hooks=[output_sink_hook],
        markdown=True,
        debug_mode=debug_mode,
    )
