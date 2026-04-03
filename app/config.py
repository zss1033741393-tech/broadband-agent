import os
import yaml
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class LLMConfig(BaseModel):
    """单个 Stage 的 LLM 配置"""

    api_key: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int


class PipelineConfig(BaseModel):
    """Pipeline 运行参数"""

    max_retry_on_constraint_fail: int = 3
    stage2_parallel: bool = False
    enable_stage3: bool = True
    enable_stage4: bool = True


def load_llm_config(stage: str) -> LLMConfig:
    """按 Stage 加载模型配置，fallback 到 default

    Args:
        stage: Stage 标识，如 "stage1_intent"、"stage2_plan"

    Returns:
        对应 Stage 的 LLMConfig
    """
    config_path = "configs/llm.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    stage_cfg = cfg.get("stages", {}).get(stage, {})
    default_cfg = cfg["default"]

    # api_key：优先 yaml 中的值，留空则 fallback 到环境变量 LLM_API_KEY
    api_key = (
        stage_cfg.get("api_key")
        or default_cfg.get("api_key")
        or os.getenv("LLM_API_KEY", "")
    )

    return LLMConfig(
        api_key=api_key,
        base_url=stage_cfg.get("base_url", default_cfg["base_url"]),
        model=stage_cfg.get("model", default_cfg["model"]),
        temperature=stage_cfg.get("temperature", default_cfg["temperature"]),
        max_tokens=stage_cfg.get("max_tokens", default_cfg["max_tokens"]),
    )


def load_pipeline_config() -> PipelineConfig:
    """加载 Pipeline 运行参数"""
    config_path = "configs/pipeline.yaml"
    if not os.path.exists(config_path):
        return PipelineConfig()

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    pipeline_cfg = cfg.get("pipeline", {})
    return PipelineConfig(**pipeline_cfg)


def load_skill(stage: str, skill_name: str) -> str:
    """从文件加载 Skill 内容

    Args:
        stage: Stage 目录名，如 "stage1"、"stage2"
        skill_name: Skill 文件名（不含 .md 后缀）

    Returns:
        Skill Markdown 文件内容
    """
    skill_path = f"skills/{stage}/{skill_name}.md"
    if not os.path.exists(skill_path):
        return ""
    with open(skill_path) as f:
        return f.read()
