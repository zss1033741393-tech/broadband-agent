"""
constraint_tools 单元测试

运行：pytest tests/test_tools/test_constraint_tools.py -v
"""

import pytest

from app.tools.constraint_tools import (
    _time_in_range,
    check_conflict,
    check_network_topology,
    check_performance,
)


class TestCheckPerformance:
    def test_valid_parameters_pass(self):
        plan = {
            "cei_perception_plan": {
                "warning_threshold": {
                    "latency_ms": 50,
                    "packet_loss_rate": 0.01,
                },
                "perception_granularity": {"sampling_interval_sec": 60},
            },
            "remote_closure_plan": {
                "closure_strategy": {"max_retry": 3}
            },
        }
        result = check_performance(plan)
        assert result["passed"] is True
        assert len(result["violations"]) == 0

    def test_out_of_range_latency_fails(self):
        plan = {
            "cei_perception_plan": {
                "warning_threshold": {"latency_ms": 10}  # 低于 20 的下限
            }
        }
        result = check_performance(plan)
        assert result["passed"] is False
        rules = [v["rule"] for v in result["violations"]]
        assert "RANGE-001" in rules


class TestCheckNetworkTopology:
    def test_conflicting_auto_execute_and_approval(self):
        plan = {
            "remote_closure_plan": {
                "closure_strategy": {
                    "auto_execute": True,
                    "approval_required": True,
                }
            }
        }
        result = check_network_topology(plan)
        assert result["passed"] is False
        rules = [v["rule"] for v in result["violations"]]
        assert "LOGIC-001" in rules

    def test_valid_closure_strategy_passes(self):
        plan = {
            "remote_closure_plan": {
                "closure_strategy": {
                    "auto_execute": True,
                    "approval_required": False,
                }
            }
        }
        result = check_network_topology(plan)
        assert result["passed"] is True


class TestCheckConflict:
    def test_firmware_upgrade_with_auto_execute_fails(self):
        plans = {
            "remote_closure_plan": {
                "closure_options": {"firmware_upgrade": True},
                "closure_strategy": {"auto_execute": True},
            }
        }
        result = check_conflict(plans)
        assert result["passed"] is False
        rules = [v["rule"] for v in result["violations"]]
        assert "CONFLICT-002" in rules


class TestTimeInRange:
    def test_time_in_range(self):
        assert _time_in_range("21:00", "20:00", "23:00") is True

    def test_time_out_of_range(self):
        assert _time_in_range("07:00", "20:00", "23:00") is False

    def test_boundary_values(self):
        assert _time_in_range("20:00", "20:00", "23:00") is True
        assert _time_in_range("23:00", "20:00", "23:00") is True
