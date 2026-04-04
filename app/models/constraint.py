"""约束校验结构化输出模型"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ConstraintResult(BaseModel):
    """约束校验结果 — Agent 结构化输出"""

    valid: bool = Field(description="是否全部通过校验")
    violations: list[dict] = Field(
        default_factory=list,
        description="违反的约束列表，每项含 type/message/field/severity",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="建议的修复措施",
    )
