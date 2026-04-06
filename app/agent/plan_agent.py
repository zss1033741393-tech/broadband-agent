"""PlanAgent — 五大优化方案生成（阶段2）"""
from __future__ import annotations

from agno.agent import Agent

from app.outputs.sink import output_sink_hook
from .tools import get_pipeline_file, generate_plans, discover_extra_skills

PLAN_PROMPT = """\
你是方案生成专家。处理流程：
1. 通过 get_pipeline_file("intent") 获取意图文件路径
   - 如果返回 error，必须停止并将错误反馈给用户，不得继续
2. 调用 generate_plans(intent_file=<上一步获取的路径>) 填充五大方案模板：
   体验感知方案 / 故障诊断方案 / 远程闭环处置方案 / 智能动态优化方案 / 人工兜底方案
3. 生成完成后返回方案摘要（changes 列表），不执行其他操作
4. 若收到约束建议（suggestions），按建议调整参数后重新生成，无需等待用户确认

严禁事项：
- 禁止在 get_pipeline_file 返回 error 时自行编造意图数据继续生成方案
- 禁止跳过 generate_plans 工具自行构造方案 JSON
- 所有方案数据必须来自工具调用的真实返回值
"""


def build_plan_agent(model, num_history_runs: int, debug_mode: bool) -> Agent:
    return Agent(
        name="PlanAgent",
        role="方案生成",
        model=model,
        skills=discover_extra_skills(),
        tools=[get_pipeline_file, generate_plans],
        instructions=PLAN_PROMPT,
        add_history_to_context=True,
        num_history_runs=num_history_runs,
        tool_hooks=[output_sink_hook],
        markdown=True,
        debug_mode=debug_mode,
    )
