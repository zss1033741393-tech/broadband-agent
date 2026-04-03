from pydantic import BaseModel, Field
from typing import Any, Optional


class ChangedField(BaseModel):
    """模板填充时修改的字段记录"""

    field: str = Field(description="字段路径，如 warning_threshold.latency_ms")
    from_value: Any = Field(alias="from", description="原值")
    to_value: Any = Field(alias="to", description="新值")
    reason: str = Field(description="调整原因")

    model_config = {"populate_by_name": True}


class FilledPlan(BaseModel):
    """单个填充后的方案"""

    template_name: str = Field(description="模板名称")
    filled_plan: dict[str, Any] = Field(description="填充后的方案 JSON")
    changed_fields: list[ChangedField] = Field(default_factory=list, description="修改字段列表")


class PlanFillResult(BaseModel):
    """Stage2 输出：5 个方案填充结果"""

    intent_goal_snapshot: dict[str, Any] = Field(description="本次使用的 IntentGoal 快照")
    plans: list[FilledPlan] = Field(description="5 个填充后的方案")
    retry_count: int = Field(default=0, description="因约束校验回退的次数")


class ConstraintViolation(BaseModel):
    """约束违规记录"""

    rule: str = Field(description="规则 ID，如 CONFLICT-001")
    plan: str = Field(description="涉及的方案名")
    field: str = Field(description="涉及的字段")
    reason: str = Field(description="违规原因")
    suggestion: str = Field(description="修改建议")


class ConstraintCheckResult(BaseModel):
    """Stage3 输出：约束校验结果"""

    passed: bool = Field(description="是否通过校验")
    violations: list[ConstraintViolation] = Field(default_factory=list, description="违规列表")
    retry_hint: str = Field(default="", description="回退给 Stage2 的调整指令")
