"""ConstraintAgent — 约束校验（阶段3）"""
from __future__ import annotations

from agno.agent import Agent

from app.outputs.sink import output_sink_hook
from .tools import get_pipeline_file, check_constraints, discover_extra_skills

CONSTRAINT_PROMPT = """\
你是约束校验专家。处理流程：
1. 调用 check_constraints(get_pipeline_file("plans")) 执行约束校验
   - intent_goal 可省略，工具自动从 intent.json 读取
   - 如果 get_pipeline_file 返回 error，必须停止并反馈错误，不得继续
2. 返回校验结果：
   - passed=true → 返回"校验通过"
   - conflicts 非空 → 返回 suggestions 列表，主控将据此重新生成方案
   - warnings 非空 → 返回警告内容，由主控询问用户确认
3. 不执行校验以外的操作

严禁事项：
- 禁止在输入文件缺失时自行编造校验结果（如伪造 passed=true）
- 禁止跳过 check_constraints 工具自行构造校验 JSON
- 工具返回 error 时必须如实反馈，不得忽略或篡改

回复要求：完成后只返回 2-3 句话的关键摘要（如"校验通过，无冲突无警告"或"发现 1 个冲突: ..."），
不要回顾完整 JSON 数据。详细数据已落盘到 outputs/ 供下游读取。
"""


def build_constraint_agent(model, num_history_runs: int, debug_mode: bool) -> Agent:
    return Agent(
        name="ConstraintAgent",
        role="约束校验",
        model=model,
        skills=discover_extra_skills(),
        tools=[get_pipeline_file, check_constraints],
        instructions=CONSTRAINT_PROMPT,
        add_history_to_context=True,
        num_history_runs=num_history_runs,
        tool_hooks=[output_sink_hook],
        markdown=True,
        debug_mode=debug_mode,
    )
