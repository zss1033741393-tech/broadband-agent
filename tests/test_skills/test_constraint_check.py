"""约束校验 Skill 单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.constraint_checker.scripts.validate import (
    check_conflict_constraints,
    check_performance_constraints,
    run_all_checks,
)


def _make_plans(
    sampling_interval: int = 300,
    auto_diag: bool = False,
    energy_time: str = "02:00",
    roaming: bool = False,
    coverage: bool = False,
) -> dict:
    return {
        "cei_perception.json": {
            "filled_data": {
                "cei_perception": {
                    "perception_granularity": {
                        "sampling_interval_sec": sampling_interval,
                        "per_user_enabled": False,
                    },
                    "warning_threshold": {"latency_ms": 100},
                }
            }
        },
        "fault_diagnosis.json": {
            "filled_data": {
                "fault_diagnosis": {
                    "auto_diagnosis": {"enabled": auto_diag}
                }
            }
        },
        "dynamic_optimization.json": {
            "filled_data": {
                "dynamic_optimization": {
                    "energy_saving": {"enabled": True, "trigger_time": energy_time},
                    "wifi_optimization": {
                        "roaming_optimization": roaming,
                        "coverage_optimization": coverage,
                    },
                }
            }
        },
    }


def test_performance_check_passes() -> None:
    plans = _make_plans(sampling_interval=300)
    failures = check_performance_constraints(plans)
    assert failures == []


def test_performance_check_fails_low_interval() -> None:
    plans = _make_plans(sampling_interval=20)
    failures = check_performance_constraints(plans)
    assert any(f["id"] == "PERF_001" for f in failures)


def test_conflict_check_energy_overlap() -> None:
    plans = _make_plans(energy_time="20:00")
    intent = {"guarantee_period": {"start_time": "19:00", "end_time": "23:00"}}
    conflicts = check_conflict_constraints(plans, intent)
    assert any(c["id"] == "CONF_001" for c in conflicts)


def test_conflict_check_wifi_conflict() -> None:
    plans = _make_plans(roaming=True, coverage=True)
    intent = {"guarantee_period": {"start_time": "00:00", "end_time": "23:59"}}
    conflicts = check_conflict_constraints(plans, intent)
    assert any(c["id"] == "CONF_002" for c in conflicts)


def test_run_all_checks_passes() -> None:
    plans = _make_plans()
    intent = {"guarantee_period": {"start_time": "19:00", "end_time": "23:00"}}
    result = run_all_checks(plans, intent)
    assert result["passed"] is True
