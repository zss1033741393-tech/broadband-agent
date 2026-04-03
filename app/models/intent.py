"""意图相关 Pydantic 模型"""
from typing import Optional

from pydantic import BaseModel, Field


class GuaranteePeriod(BaseModel):
    start_time: str = Field(default="00:00", description="保障开始时间 HH:MM")
    end_time: str = Field(default="23:59", description="保障结束时间 HH:MM")
    is_periodic: bool = Field(default=False, description="是否周期性保障")


class GuaranteeTarget(BaseModel):
    priority_level: str = Field(default="medium", description="优先级 high/medium/low")
    sensitivity: str = Field(default="", description="用户敏感点")
    key_applications: list[str] = Field(default_factory=list, description="关键应用列表")


class CoreMetrics(BaseModel):
    latency_sensitive: bool = Field(default=False, description="延迟敏感")
    bandwidth_priority: bool = Field(default=False, description="带宽优先")
    stability_priority: bool = Field(default=False, description="稳定性优先")


class IntentGoal(BaseModel):
    user_type: str = Field(default="", description="用户类型，如直播用户/游戏用户/办公用户")
    scenario: str = Field(default="", description="保障场景")
    guarantee_period: GuaranteePeriod = Field(default_factory=GuaranteePeriod)
    guarantee_target: GuaranteeTarget = Field(default_factory=GuaranteeTarget)
    core_metrics: CoreMetrics = Field(default_factory=CoreMetrics)
    resolution_requirement: Optional[str] = Field(default=None, description="分辨率要求")

    def is_complete(self) -> bool:
        """检查意图目标是否完整"""
        return bool(self.user_type and self.scenario and self.guarantee_target.priority_level)

    def missing_fields(self) -> list[str]:
        """返回缺失的必填字段列表"""
        missing = []
        if not self.user_type:
            missing.append("user_type")
        if not self.scenario:
            missing.append("scenario")
        if not self.guarantee_target.priority_level:
            missing.append("guarantee_target.priority_level")
        return missing
