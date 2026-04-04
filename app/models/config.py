"""配置转译结构化输出模型"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigOutput(BaseModel):
    """设备配置转译结果 — Agent 结构化输出"""

    configs: dict[str, dict] = Field(description="各配置类型 → 设备配置 JSON")
    rollback_configs: dict = Field(default_factory=dict, description="回退配置")
    status: str = Field(default="completed", description="completed / failed")
