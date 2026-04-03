"""配置转译相关 Pydantic 模型"""
from typing import Any

from pydantic import BaseModel, Field


class DeviceConfig(BaseModel):
    config_type: str = Field(description="配置类型: perception/diagnosis/closure/optimization")
    device_id: str = Field(default="", description="目标设备 ID")
    config_data: dict[str, Any] = Field(default_factory=dict, description="设备配置数据")
    version: str = Field(default="1.0", description="配置版本")


class TranslationResult(BaseModel):
    configs: list[DeviceConfig] = Field(default_factory=list, description="设备配置列表")
    success: bool = Field(default=True, description="转译是否成功")
    failed_fields: list[str] = Field(default_factory=list, description="转译失败的字段")
