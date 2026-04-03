from pydantic import BaseModel, Field
from typing import Any, Optional


class PerceptionConfig(BaseModel):
    """感知粒度配置"""

    config_type: str = Field(default="perception")
    version: str = Field(default="1.0")
    thresholds: dict[str, Any] = Field(default_factory=dict)
    collection: dict[str, Any] = Field(default_factory=dict)
    schedule: dict[str, str] = Field(default_factory=dict)


class DiagnosisConfig(BaseModel):
    """故障诊断配置"""

    config_type: str = Field(default="diagnosis")
    version: str = Field(default="1.0")
    methods: dict[str, bool] = Field(default_factory=dict)
    trigger: dict[str, Any] = Field(default_factory=dict)


class ClosureConfig(BaseModel):
    """远程闭环配置"""

    config_type: str = Field(default="closure")
    version: str = Field(default="1.0")
    actions: dict[str, bool] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    audit: dict[str, Any] = Field(default_factory=dict)


class OptimizationConfig(BaseModel):
    """智能动态优化配置"""

    config_type: str = Field(default="optimization")
    version: str = Field(default="1.0")
    realtime: dict[str, Any] = Field(default_factory=dict)
    prediction: dict[str, Any] = Field(default_factory=dict)


class PipelineOutput(BaseModel):
    """Pipeline 最终输出：4 类配置 + 元数据"""

    session_id: str = Field(description="会话 ID")
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)
    diagnosis: DiagnosisConfig = Field(default_factory=DiagnosisConfig)
    closure: ClosureConfig = Field(default_factory=ClosureConfig)
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)
    output_files: list[str] = Field(default_factory=list, description="导出的配置文件路径")
    validation_passed: bool = Field(default=False, description="配置格式校验是否通过")
