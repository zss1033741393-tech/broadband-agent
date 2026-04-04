"""意图结构化输出模型"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class IntentGoal(BaseModel):
    """意图解析结果 — Agent 结构化输出"""

    intent_type: str = Field(description="意图类型，如 live_streaming/gaming/office")
    confidence: float = Field(default=1.0, description="意图识别置信度 0~1")
    entities: dict = Field(default_factory=dict, description="提取的实体（时段、应用、用户类型等）")
    missing_info: list[str] = Field(default_factory=list, description="缺失的必要信息字段")
    needs_clarification: bool = Field(default=False, description="是否需要追问用户")
    followup_question: Optional[str] = Field(default=None, description="追问话术（needs_clarification=true 时有值）")
