"""统一配置加载 — 从 configs/*.yaml 读取，全部通过 load_config() 获取"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

CONFIG_DIR = Path(__file__).parent.parent / "configs"


class LLMConfig(BaseModel):
    api_key: str
    base_url: str | None = None
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096
    provider: str = "openai"  # openai（含 OpenAI 兼容接口）| anthropic
    # 是否启用 Agno 推理链（仅原生推理模型开启：deepseek-reasoner / OpenAI o1/o3）
    # 普通 OpenAI 兼容模型（qwen、gpt-4o、claude 等）保持 false
    reasoning: bool = False


class StorageConfig(BaseModel):
    sqlite_db_path: str = "./data/agent.db"
    sqlite_table: str = "agent_sessions"
    lancedb_uri: str = "./data/lancedb"
    lancedb_table: str = "domain_knowledge"


class AgentConfig(BaseModel):
    """单个子 Agent 的运行参数"""
    num_history_runs: int
    model: str | None = None  # None = 继承主控 llm.yaml 中的模型


class AgentsConfig(BaseModel):
    """四个子 Agent 的独立配置，支持各自使用不同模型和历史轮数"""
    intent: AgentConfig = AgentConfig(num_history_runs=4)
    plan: AgentConfig = AgentConfig(num_history_runs=2)
    constraint: AgentConfig = AgentConfig(num_history_runs=2)
    config: AgentConfig = AgentConfig(num_history_runs=1)


class PipelineConfig(BaseModel):
    max_turns: int = 15
    max_retry_on_constraint_fail: int = 3
    num_history_runs: int = 4  # 主控 OrchestratorTeam 的历史轮数
    skills_dir: str = "./skills"
    debug_mode: bool = True
    clarification_max_rounds: int = 3
    clarification_max_fields_per_round: int = 3
    # 预留扩展开关：True 时切换为 LLM 实现，False 时使用规则引擎（当前原型）
    use_llm_constraint: bool = False
    use_llm_translation: bool = False
    tool_timeout_sec: int = 30  # 单个工具执行超时（秒），超时返回 error 不阻塞流程
    agents: AgentsConfig = AgentsConfig()


class AppConfig(BaseModel):
    llm: LLMConfig
    storage: StorageConfig
    pipeline: PipelineConfig


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """从 configs/ 目录加载所有 YAML 配置，结果缓存"""
    with open(CONFIG_DIR / "llm.yaml", encoding="utf-8") as f:
        llm_raw = yaml.safe_load(f) or {}
    with open(CONFIG_DIR / "pipeline.yaml", encoding="utf-8") as f:
        pipeline_raw = yaml.safe_load(f) or {}

    return AppConfig(
        llm=LLMConfig(**llm_raw),
        storage=StorageConfig(**pipeline_raw.get("storage", {})),
        pipeline=PipelineConfig(**pipeline_raw.get("pipeline", {})),
    )
