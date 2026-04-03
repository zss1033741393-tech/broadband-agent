"""
app/logger/tracer.py 单元测试

测试从 mock RunResponse 中提取 LLM 调用信息的逻辑，无需 LLM API。
运行：pytest tests/test_tools/test_tracer.py -v
"""

from unittest.mock import MagicMock

import pytest

from app.logger.tracer import _extract_messages, _extract_usage, _normalize_content


class TestNormalizeContent:
    def test_string_passthrough(self):
        assert _normalize_content("hello") == "hello"

    def test_none_returns_empty(self):
        assert _normalize_content(None) == ""

    def test_list_extracts_text(self):
        content = [{"type": "text", "text": "part1"}, {"type": "text", "text": "part2"}]
        result = _normalize_content(content)
        assert "part1" in result
        assert "part2" in result

    def test_non_text_type_in_list_skipped(self):
        content = [{"type": "image_url", "url": "..."}, {"type": "text", "text": "hi"}]
        result = _normalize_content(content)
        assert result == "hi"


class TestExtractMessages:
    def _make_msg(self, role: str, content: str = "", **kwargs) -> MagicMock:
        msg = MagicMock()
        msg.role = role
        msg.content = content
        msg.tool_calls = []
        msg.tool_call_id = ""
        msg.name = ""
        for attr in ("reasoning_content", "thinking", "reasoning"):
            setattr(msg, attr, None)
        for k, v in kwargs.items():
            setattr(msg, k, v)
        return msg

    def test_system_and_user_go_to_request(self):
        response = MagicMock()
        response.content = ""
        response.messages = [
            self._make_msg("system", "你是助手"),
            self._make_msg("user", "帮我优化网络"),
        ]
        req_msgs, resp, reasoning, tc, tr = _extract_messages(response)
        assert len(req_msgs) == 2
        assert req_msgs[0]["role"] == "system"
        assert req_msgs[1]["role"] == "user"
        assert resp == ""

    def test_assistant_content_extracted(self):
        response = MagicMock()
        response.content = ""
        response.messages = [
            self._make_msg("assistant", "好的，已生成方案"),
        ]
        _, resp, _, _, _ = _extract_messages(response)
        assert resp == "好的，已生成方案"

    def test_reasoning_content_extracted(self):
        response = MagicMock()
        response.content = ""
        msg = self._make_msg("assistant", "最终答案")
        msg.reasoning_content = "首先分析用户需求..."
        response.messages = [msg]
        _, _, reasoning, _, _ = _extract_messages(response)
        assert reasoning == "首先分析用户需求..."

    def test_tool_call_extracted(self):
        response = MagicMock()
        response.content = ""
        tc = MagicMock()
        tc.id = "call_001"
        tc.function.name = "load_template"
        tc.function.arguments = '{"template_name": "cei"}'
        msg = self._make_msg("assistant", "")
        msg.tool_calls = [tc]
        response.messages = [msg]
        _, _, _, tool_calls, _ = _extract_messages(response)
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "load_template"
        assert tool_calls[0]["id"] == "call_001"

    def test_tool_result_extracted(self):
        response = MagicMock()
        response.content = ""
        msg = self._make_msg("tool", '{"latency_ms": 50}')
        msg.tool_call_id = "call_001"
        msg.name = "load_template"
        response.messages = [msg]
        _, _, _, _, tool_results = _extract_messages(response)
        assert len(tool_results) == 1
        assert tool_results[0]["tool_call_id"] == "call_001"

    def test_fallback_to_response_content(self):
        """messages 为空时 fallback 到 response.content"""
        response = MagicMock()
        response.content = "直接回复"
        response.messages = []
        _, resp, _, _, _ = _extract_messages(response)
        assert resp == "直接回复"


class TestExtractUsage:
    def test_extract_from_metrics_dict(self):
        response = MagicMock()
        response.metrics = {"input_tokens": 100, "output_tokens": 50}
        response.usage = None
        tokens_in, tokens_out, tokens_reasoning = _extract_usage(response)
        assert tokens_in == 100
        assert tokens_out == 50
        assert tokens_reasoning is None

    def test_extract_reasoning_tokens(self):
        response = MagicMock()
        response.metrics = {
            "input_tokens": 200,
            "output_tokens": 80,
            "reasoning_tokens": 300,
        }
        response.usage = None
        _, _, tokens_reasoning = _extract_usage(response)
        assert tokens_reasoning == 300

    def test_fallback_to_usage_object(self):
        response = MagicMock()
        response.metrics = {}
        response.usage.prompt_tokens = 150
        response.usage.completion_tokens = 60
        response.usage.completion_tokens_details = None
        tokens_in, tokens_out, _ = _extract_usage(response)
        assert tokens_in == 150
        assert tokens_out == 60

    def test_no_usage_returns_none(self):
        response = MagicMock()
        response.metrics = {}
        response.usage = None
        tokens_in, tokens_out, tokens_reasoning = _extract_usage(response)
        assert tokens_in is None
        assert tokens_out is None
        assert tokens_reasoning is None
