"""约束校验脚本 — 性能/组网/冲突三类校验"""
import json
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parent.parent
REFERENCES_DIR = SKILL_DIR / "references"


def _load_rules(filename: str) -> dict[str, Any]:
    return json.loads((REFERENCES_DIR / filename).read_text(encoding="utf-8"))


def check_performance_constraints(plans: dict[str, Any]) -> list[dict[str, Any]]:
    """
    性能约束校验。

    Returns:
        失败的校验项列表，每项包含 id/message/severity
    """
    rules_data = _load_rules("performance_rules.json")
    failures: list[dict[str, Any]] = []

    cei = plans.get("cei_perception.json", {}).get("filled_data", {}).get("cei_perception", {})
    granularity = cei.get("perception_granularity", {})
    sampling = granularity.get("sampling_interval_sec", 300)

    # PERF_001: 采集间隔不能低于 30 秒
    if sampling < 30:
        failures.append({
            "id": "PERF_001",
            "message": "采集间隔不能低于 30 秒，否则网关 CPU 负载过高",
            "severity": "error",
        })

    # PERF_003: 自动诊断开启时，采集间隔建议不低于 60 秒
    diag = plans.get("fault_diagnosis.json", {}).get("filled_data", {}).get("fault_diagnosis", {})
    auto_diag = diag.get("auto_diagnosis", {}).get("enabled", False)
    if auto_diag and sampling < 60:
        failures.append({
            "id": "PERF_003",
            "message": "自动诊断开启时，采集间隔建议不低于 60 秒",
            "severity": "warning",
        })

    return failures


def check_conflict_constraints(
    plans: dict[str, Any],
    intent_goal: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    方案冲突检测。

    Returns:
        检测到的冲突列表，每项包含 id/message/severity/suggestion
    """
    conflicts: list[dict[str, Any]] = []

    opt = plans.get("dynamic_optimization.json", {}).get("filled_data", {}).get(
        "dynamic_optimization", {}
    )
    energy = opt.get("energy_saving", {})
    wifi = opt.get("wifi_optimization", {})

    # CONF_001: 节能时段与保障时段冲突
    guarantee_period = intent_goal.get("guarantee_period", {})
    g_start = guarantee_period.get("start_time", "00:00")
    g_end = guarantee_period.get("end_time", "23:59")
    energy_trigger = energy.get("trigger_time", "02:00")
    if energy.get("enabled") and _time_in_range(energy_trigger, g_start, g_end):
        conflicts.append({
            "id": "CONF_001",
            "message": f"节能触发时间 {energy_trigger} 与保障时段 {g_start}-{g_end} 重叠",
            "severity": "error",
            "suggestion": "将节能触发时间调整到保障时段之外",
        })

    # CONF_002: WiFi 漫游与覆盖优化冲突
    if wifi.get("roaming_optimization") and wifi.get("coverage_optimization"):
        conflicts.append({
            "id": "CONF_002",
            "message": "WiFi 漫游优化与覆盖优化不能同时开启",
            "severity": "error",
            "suggestion": "关闭 coverage_optimization，保留 roaming_optimization",
        })

    return conflicts


def run_all_checks(
    plans: dict[str, Any],
    intent_goal: dict[str, Any],
) -> dict[str, Any]:
    """
    执行所有约束校验，返回综合结果。

    Args:
        plans: 填充后的方案字典，key 为模板文件名
        intent_goal: 意图目标

    Returns:
        {passed, conflicts, warnings, failed_checks}
    """
    perf_failures = check_performance_constraints(plans)
    conf_conflicts = check_conflict_constraints(plans, intent_goal)

    all_issues = perf_failures + conf_conflicts
    errors = [i for i in all_issues if i.get("severity") == "error"]
    warnings = [i for i in all_issues if i.get("severity") == "warning"]

    return {
        "passed": len(errors) == 0,
        "conflicts": [f"{i['id']}: {i['message']}" for i in errors],
        "warnings": [f"{i['id']}: {i['message']}" for i in warnings],
        "failed_checks": [i["id"] for i in errors],
        "suggestions": [i.get("suggestion", "") for i in errors if i.get("suggestion")],
    }


def _time_in_range(time_str: str, start: str, end: str) -> bool:
    """判断 time_str 是否在 start-end 范围内（简单字符串比较）"""
    if start <= end:
        return start <= time_str <= end
    # 跨午夜情况
    return time_str >= start or time_str <= end


if __name__ == "__main__":
    """CLI 入口 — 供 get_skill_script(execute=True) 调用

    用法:
        python validate.py '<plans_json>' '<intent_goal_json>'

    输出: JSON 字符串，含 passed / conflicts / warnings / suggestions
    """
    import sys

    plans_json = sys.argv[1] if len(sys.argv) > 1 else "{}"
    intent_goal_json = sys.argv[2] if len(sys.argv) > 2 else "{}"

    try:
        plans = json.loads(plans_json)
    except json.JSONDecodeError:
        print(json.dumps({"error": "plans_json 格式错误"}, ensure_ascii=False))
        sys.exit(1)

    try:
        intent_goal = json.loads(intent_goal_json)
    except json.JSONDecodeError:
        intent_goal = {}

    result = run_all_checks(plans, intent_goal)
    print(json.dumps(result, ensure_ascii=False))
