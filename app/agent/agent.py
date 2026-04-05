"""Agent 入口 — 向后兼容包装层

实际实现已拆分为多 Agent 架构，见 app/agent/team.py：
  IntentAgent / PlanAgent / ConstraintAgent / ConfigAgent → 各阶段专家
  OrchestratorTeam → 主控（TeamMode.coordinate）

本模块保留以下符号供测试和外部代码兼容导入：
  get_agent()        → 返回 OrchestratorTeam（Agno Team 与 Agent 接口一致）
  SKILLS_DIR         → skills/ 目录绝对路径
  SYSTEM_PROMPT      → 主控 system prompt（即 ORCHESTRATOR_PROMPT）
  discover_skills()  → 扫描所有 Skill 目录（测试用）
  build_agent()      → 构建 Team（向后兼容别名）
  _build_model()     → 按 provider 构建模型
"""
from __future__ import annotations

import logging
from pathlib import Path

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.skills import LocalSkills, Skills
from agno.team import Team

from app.config import LLMConfig, load_config
from .team import (
    build_team,
    get_team,
    _build_model,
    ORCHESTRATOR_PROMPT,
)
from .tools import SKILLS_DIR, get_pipeline_file, check_constraints, translate_configs

logger = logging.getLogger("agent")
cfg = load_config()

# ── 向后兼容符号 ──────────────────────────────────────────────

SYSTEM_PROMPT = ORCHESTRATOR_PROMPT


def discover_skills(skills_dir: Path) -> Skills:
    """扫描 skills/ 下所有含 SKILL.md 的子目录，逐一注册为 LocalSkills（测试/调试用）"""
    loaders = []
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists():
            loaders.append(LocalSkills(path=str(child), validate=False))
    logger.info("发现 Skills: %s", [c.name for c in sorted(skills_dir.iterdir())
                                     if c.is_dir() and (c / "SKILL.md").exists()])
    return Skills(loaders=loaders)


def build_agent() -> Team:
    """构建 OrchestratorTeam（向后兼容别名，等同于 build_team()）"""
    return build_team()


def get_agent() -> Team:
    """返回 OrchestratorTeam 单例（向后兼容别名，等同于 get_team()）"""
    return get_team()
