"""
Stage1 IntentParser Agent 测试

运行：pytest tests/test_agents/test_intent_agent.py -v
注意：需要配置 LLM_API_KEY 才能运行集成测试
"""

import pytest

from app.models.intent import IntentGoal


class TestIntentGoalModel:
    """IntentGoal 数据模型单元测试（无需 LLM）"""

    def test_default_values(self):
        goal = IntentGoal()
        assert goal.user_type == ""
        assert goal.need_followup is False
        assert goal.missing_fields == []

    def test_serialize_deserialize(self):
        goal = IntentGoal(
            user_type="直播用户",
            scenario="直播推流保障",
        )
        data = goal.model_dump()
        restored = IntentGoal.model_validate(data)
        assert restored.user_type == "直播用户"
        assert restored.scenario == "直播推流保障"

    def test_core_metrics_defaults(self):
        goal = IntentGoal()
        assert goal.core_metrics.latency_sensitive is False
        assert goal.core_metrics.bandwidth_priority is False
        assert goal.core_metrics.stability_priority is False


@pytest.mark.integration
class TestIntentAgentIntegration:
    """集成测试（需要 LLM API）"""

    @pytest.mark.asyncio
    async def test_parse_livestream_intent(self):
        """测试直播用户意图解析"""
        from app.agents.intent_agent import parse_intent

        intent = await parse_intent("我家里有直播需求，晚上 8 点到 11 点经常卡顿")
        assert intent.user_type != ""
        assert "直播" in intent.user_type or intent.guarantee_target.priority_level == "high"

    @pytest.mark.asyncio
    async def test_missing_period_triggers_followup(self):
        """测试缺少时段信息时触发追问"""
        from app.agents.intent_agent import parse_intent

        intent = await parse_intent("我打游戏延迟很高")
        # 应该识别为游戏用户，可能需要追问时段
        assert intent.user_type != "" or intent.need_followup is True
