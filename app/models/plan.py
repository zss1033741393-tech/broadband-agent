"""方案填充结构化输出模型"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PlanResult(BaseModel):
    """五大方案填充结果 — Agent 结构化输出"""

    plans: dict[str, dict] = Field(description="各方案名称 → 填充后的模板 JSON")
    changes_summary: list[dict] = Field(
        default_factory=list,
        description="各方案修改摘要，每项含 plan_name/field/old_value/new_value",
    )
