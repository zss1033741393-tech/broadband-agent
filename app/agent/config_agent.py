"""ConfigAgent — 配置转译，生成 4 类设备配置（阶段4）"""
from __future__ import annotations

from agno.agent import Agent
from agno.skills import LocalSkills, Skills

from app.config import load_config
from .tools import get_pipeline_file, translate_configs, SKILLS_DIR

cfg = load_config()

CONFIG_PROMPT = """\
你是配置转译专家。处理流程：
1. 调用 translate_configs(get_pipeline_file("plans")) 生成 4 类设备配置：
   perception（感知粒度）/ diagnosis（故障诊断）/ closure（远程闭环）/ optimization（动态优化）
2. 返回配置摘要：各配置类型的关键参数值
3. 若 failed_fields 非空，说明部分字段转译失败，告知用户
4. 告知用户回退方案（如何恢复默认值）
5. 不执行配置转译以外的操作
"""


def build_config_agent(model) -> Agent:
    skills = Skills(loaders=[
        LocalSkills(path=str(SKILLS_DIR / "config_translator"), validate=False),
    ])
    return Agent(
        name="ConfigAgent",
        role="配置转译",
        model=model,
        skills=skills,
        tools=[get_pipeline_file, translate_configs],
        instructions=CONFIG_PROMPT,
        add_history_to_context=True,
        num_history_runs=1,
        markdown=True,
        debug_mode=cfg.pipeline.debug_mode,
    )
