"""ConfigAgent — 配置转译，生成 4 类设备配置（阶段4）"""
from __future__ import annotations

from agno.agent import Agent

from app.outputs.sink import output_sink_hook
from .tools import get_pipeline_file, translate_configs, discover_extra_skills

CONFIG_PROMPT = """\
你是配置转译专家。处理流程：
1. 调用 translate_configs(get_pipeline_file("plans")) 生成 4 类设备配置：
   perception（感知粒度）/ diagnosis（故障诊断）/ closure（远程闭环）/ optimization（动态优化）
   - 如果 get_pipeline_file 返回 error，必须停止并反馈错误，不得继续
2. 返回配置摘要：各配置类型的关键参数值
3. 若 failed_fields 非空，说明部分字段转译失败，告知用户
4. 告知用户回退方案（如何恢复默认值）
5. 不执行配置转译以外的操作

严禁事项：
- 禁止在输入文件缺失时自行编造设备配置数据
- 禁止跳过 translate_configs 工具自行构造配置 JSON
- 工具返回 error 时必须如实反馈，不得忽略或篡改
"""


def build_config_agent(model, num_history_runs: int, debug_mode: bool) -> Agent:
    return Agent(
        name="ConfigAgent",
        role="配置转译",
        model=model,
        skills=discover_extra_skills(),
        tools=[get_pipeline_file, translate_configs],
        instructions=CONFIG_PROMPT,
        add_history_to_context=True,
        num_history_runs=num_history_runs,
        tool_hooks=[output_sink_hook],
        markdown=True,
        debug_mode=debug_mode,
    )
