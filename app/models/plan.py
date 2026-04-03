"""方案相关 Pydantic 模型"""
from typing import Any, Optional

from pydantic import BaseModel, Field


class PlanResult(BaseModel):
    plan_name: str = Field(description="方案名称")
    filled_data: dict[str, Any] = Field(default_factory=dict, description="填充后的方案数据")
    changes: list[str] = Field(default_factory=list, description="相对于默认模板的修改列表")
    status: str = Field(default="pending", description="状态: pending/filled/failed")
    error: Optional[str] = Field(default=None, description="填充失败原因")


class PlanFillResult(BaseModel):
    plans: list[PlanResult] = Field(default_factory=list, description="五大方案填充结果")
    success_count: int = Field(default=0, description="成功填充的方案数量")
    failed_count: int = Field(default=0, description="失败的方案数量")


class ConstraintCheckResult(BaseModel):
    passed: bool = Field(description="是否通过校验")
    conflicts: list[str] = Field(default_factory=list, description="冲突列表")
    warnings: list[str] = Field(default_factory=list, description="警告列表")
    failed_checks: list[str] = Field(default_factory=list, description="失败的校验项")
