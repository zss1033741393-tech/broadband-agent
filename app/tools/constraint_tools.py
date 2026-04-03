from typing import Any


def check_performance(plan: dict, device_info: dict | None = None) -> dict:
    """校验方案中的参数范围约束（不依赖设备信息的静态规则）

    Args:
        plan: 填充后的方案 dict
        device_info: 设备信息（可选，原型阶段暂不使用）

    Returns:
        {"passed": bool, "violations": list}
    """
    violations = []

    # CEI 方案参数范围校验
    cei = plan.get("cei_perception_plan", {})
    thresholds = cei.get("warning_threshold", {})

    latency = thresholds.get("latency_ms")
    if latency is not None and not (20 <= latency <= 500):
        violations.append({
            "rule": "RANGE-001",
            "plan": "cei_perception_plan",
            "field": "warning_threshold.latency_ms",
            "reason": f"latency_ms={latency} 超出合理范围 [20, 500]",
            "suggestion": f"将 latency_ms 调整到 [20, 500] 之间",
        })

    loss_rate = thresholds.get("packet_loss_rate")
    if loss_rate is not None and not (0.001 <= loss_rate <= 0.1):
        violations.append({
            "rule": "RANGE-002",
            "plan": "cei_perception_plan",
            "field": "warning_threshold.packet_loss_rate",
            "reason": f"packet_loss_rate={loss_rate} 超出合理范围 [0.001, 0.1]",
            "suggestion": "将 packet_loss_rate 调整到 [0.001, 0.1] 之间",
        })

    granularity = cei.get("perception_granularity", {})
    interval = granularity.get("sampling_interval_sec")
    if interval is not None and not (30 <= interval <= 3600):
        violations.append({
            "rule": "RANGE-003",
            "plan": "cei_perception_plan",
            "field": "perception_granularity.sampling_interval_sec",
            "reason": f"sampling_interval_sec={interval} 超出合理范围 [30, 3600]",
            "suggestion": "将 sampling_interval_sec 调整到 [30, 3600] 之间",
        })

    # 远程闭环方案参数范围校验
    closure = plan.get("remote_closure_plan", {})
    strategy = closure.get("closure_strategy", {})

    max_retry = strategy.get("max_retry")
    if max_retry is not None and not (1 <= max_retry <= 10):
        violations.append({
            "rule": "RANGE-004",
            "plan": "remote_closure_plan",
            "field": "closure_strategy.max_retry",
            "reason": f"max_retry={max_retry} 超出合理范围 [1, 10]",
            "suggestion": "将 max_retry 调整到 [1, 10] 之间",
        })

    # 人工兜底方案校验
    fallback = plan.get("manual_fallback_plan", {})
    onsite = fallback.get("onsite_closure_strategy", {})
    sla = onsite.get("sla_response_hour")
    if sla is not None and not (1 <= sla <= 72):
        violations.append({
            "rule": "RANGE-005",
            "plan": "manual_fallback_plan",
            "field": "onsite_closure_strategy.sla_response_hour",
            "reason": f"sla_response_hour={sla} 超出合理范围 [1, 72]",
            "suggestion": "将 sla_response_hour 调整到 [1, 72] 之间",
        })

    return {"passed": len(violations) == 0, "violations": violations}


def check_network_topology(plan: dict, device_info: dict | None = None) -> dict:
    """校验组网方式相关约束

    Args:
        plan: 填充后的方案 dict
        device_info: 设备信息（可选）

    Returns:
        {"passed": bool, "violations": list}
    """
    violations = []

    # 逻辑约束：auto_execute 与 approval_required 互斥
    closure = plan.get("remote_closure_plan", {})
    strategy = closure.get("closure_strategy", {})
    if strategy.get("auto_execute") is True and strategy.get("approval_required") is True:
        violations.append({
            "rule": "LOGIC-001",
            "plan": "remote_closure_plan",
            "field": "closure_strategy",
            "reason": "auto_execute=true 与 approval_required=true 互斥",
            "suggestion": "高优先级场景设 auto_execute=true, approval_required=false",
        })

    # 逻辑约束：预测优化启用时学习期不能太短
    opt = plan.get("dynamic_optimization_plan", {})
    habit = opt.get("habit_pre_optimization", {})
    if habit.get("enabled") is True and habit.get("learning_period_days", 7) < 3:
        violations.append({
            "rule": "LOGIC-002",
            "plan": "dynamic_optimization_plan",
            "field": "habit_pre_optimization.learning_period_days",
            "reason": "habit_pre_optimization.enabled=true 时 learning_period_days 必须 ≥ 3",
            "suggestion": "将 learning_period_days 设为 3 或以上",
        })

    return {"passed": len(violations) == 0, "violations": violations}


def check_conflict(plans: dict) -> dict:
    """校验多方案间的策略冲突

    Args:
        plans: 包含所有方案的 dict，key 为模板名

    Returns:
        {"passed": bool, "violations": list}
    """
    violations = []

    # CONFLICT-001：节能触发时间与保障时段冲突
    app_history = plans.get("_meta", {}).get("app_history", {})
    energy_time = app_history.get("energy_saving_trigger_time", "")
    cei = plans.get("cei_perception_plan", {})
    trigger = cei.get("trigger_window", {})
    start = trigger.get("enable_time", "00:00")
    end = trigger.get("disable_time", "23:59")

    if energy_time and start != "00:00":
        if _time_in_range(energy_time, start, end):
            violations.append({
                "rule": "CONFLICT-001",
                "plan": "dynamic_optimization_plan",
                "field": "energy_saving_trigger_time",
                "reason": f"节能触发时间 {energy_time} 在用户保障时段 {start}-{end} 内",
                "suggestion": f"将节能触发时间调整到 {end} 之后",
            })

    # CONFLICT-002：高风险操作不能在保障时段内自动执行
    closure = plans.get("remote_closure_plan", {})
    closure_opts = closure.get("closure_options", {})
    closure_strategy = closure.get("closure_strategy", {})
    if closure_opts.get("firmware_upgrade") and closure_strategy.get("auto_execute"):
        violations.append({
            "rule": "CONFLICT-002",
            "plan": "remote_closure_plan",
            "field": "closure_options.firmware_upgrade",
            "reason": "firmware_upgrade 不能与 auto_execute=true 同时启用（高风险）",
            "suggestion": "将 firmware_upgrade 的 auto_execute 改为 false，需人工审批",
        })

    return {"passed": len(violations) == 0, "violations": violations}


def _time_in_range(check_time: str, start: str, end: str) -> bool:
    """判断时间字符串是否在范围内（HH:MM 格式）"""
    try:
        def to_minutes(t: str) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m)

        ct = to_minutes(check_time)
        st = to_minutes(start)
        et = to_minutes(end)
        return st <= ct <= et
    except Exception:
        return False
