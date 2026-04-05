"""Agent 入口 — 向后兼容包装层

实际实现已拆分为多 Agent 架构，见 app/agent/team.py：
  IntentAgent / PlanAgent / ConstraintAgent / ConfigAgent — 各阶段专家
  OrchestratorTeam — 主控（TeamMode.coordinate）

本模块保留以下符号供测试和外部代码兼容导入：
  get_agent()        → 返回 OrchestratorTeam 单例
  build_agent()      → 构建 Team（向后兼容别名）
  discover_skills()  → 扫描所有 Skill 目录（测试用）
  SKILLS_DIR         → skills/ 目录绝对路径
  SYSTEM_PROMPT      → 主控 system prompt
  _build_model()     → 按 provider 构建模型
"""
from __future__ import annotations

import logging
from pathlib import Path

from agno.skills import LocalSkills, Skills

from .team import (
    build_team,
    get_team,
    _build_model,
    ORCHESTRATOR_PROMPT,
)
from .tools import SKILLS_DIR

logger = logging.getLogger("agent")

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


def build_agent():
    """构建 OrchestratorTeam（向后兼容别名）"""
    return build_team()


def get_agent():
    """返回 OrchestratorTeam 单例（向后兼容别名）"""
    return get_team()
