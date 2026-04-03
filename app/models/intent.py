from pydantic import BaseModel, Field
from typing import Optional


class GuaranteePeriod(BaseModel):
    """保障时段"""

    start_time: str = Field(default="00:00", description="开始时间 HH:MM")
    end_time: str = Field(default="23:59", description="结束时间 HH:MM")
    is_periodic: bool = Field(default=False, description="是否周期性（每天重复）")


class GuaranteeTarget(BaseModel):
    """保障目标"""

    priority_level: str = Field(default="medium", description="优先级: high/medium/low")
    sensitivity: str = Field(default="", description="敏感类型: 卡顿敏感/延迟敏感/稳定优先")
    key_applications: list[str] = Field(default_factory=list, description="关键应用列表")


class CoreMetrics(BaseModel):
    """核心指标偏好"""

    latency_sensitive: bool = Field(default=False, description="是否延迟敏感")
    bandwidth_priority: bool = Field(default=False, description="是否带宽优先")
    stability_priority: bool = Field(default=False, description="是否稳定性优先")


class IntentGoal(BaseModel):
    """用户意图目标体，Stage1 的输出，Stage2 的输入"""

    user_type: str = Field(default="", description="用户类型: 直播用户/游戏用户/办公用户/普通家庭")
    scenario: str = Field(default="", description="场景描述")
    guarantee_period: GuaranteePeriod = Field(default_factory=GuaranteePeriod)
    guarantee_target: GuaranteeTarget = Field(default_factory=GuaranteeTarget)
    core_metrics: CoreMetrics = Field(default_factory=CoreMetrics)
    resolution_requirement: str = Field(default="", description="用户对问题解决的期望")

    # 追问状态
    missing_fields: list[str] = Field(default_factory=list, description="缺失的必要字段")
    need_followup: bool = Field(default=False, description="是否需要追问")
    followup_question: str = Field(default="", description="追问内容")
