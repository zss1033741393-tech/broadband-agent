import json
import os
from typing import Any

from app.models.config import (
    ClosureConfig,
    DiagnosisConfig,
    OptimizationConfig,
    PerceptionConfig,
    PipelineOutput,
)


def translate_to_config(plans: dict, session_id: str) -> PipelineOutput:
    """将语义化方案 JSON 转译为设备可执行的配置格式

    Args:
        plans: 包含所有填充方案的 dict，key 为模板名
        session_id: 会话 ID

    Returns:
        PipelineOutput 包含 4 类配置
    """
    perception = _translate_perception(plans.get("cei_perception_plan", {}))
    diagnosis = _translate_diagnosis(plans.get("fault_diagnosis_plan", {}))
    closure = _translate_closure(plans.get("remote_closure_plan", {}))
    optimization = _translate_optimization(plans.get("dynamic_optimization_plan", {}))

    return PipelineOutput(
        session_id=session_id,
        perception=perception,
        diagnosis=diagnosis,
        closure=closure,
        optimization=optimization,
    )


def _translate_perception(plan: dict) -> PerceptionConfig:
    """CEI 方案 → 感知粒度配置"""
    cfg = plan.get("cei_perception_plan", plan)
    thresholds = cfg.get("warning_threshold", {})
    granularity = cfg.get("perception_granularity", {})
    trigger = cfg.get("trigger_window", {})

    return PerceptionConfig(
        thresholds={
            "rtt_alarm_ms": thresholds.get("latency_ms", 100),
            "loss_alarm_ratio": thresholds.get("packet_loss_rate", 0.01),
            "jitter_alarm_ms": thresholds.get("jitter_ms", 30),
            "bw_min_mbps": thresholds.get("throughput_min_mbps", 50),
        },
        collection={
            "interval_sec": granularity.get("sampling_interval_sec", 300),
            "window_min": granularity.get("aggregation_window_min", 15),
            "per_user": granularity.get("per_user_enabled", False),
        },
        schedule={
            "start": trigger.get("enable_time", "00:00"),
            "end": trigger.get("disable_time", "23:59"),
        },
    )


def _translate_diagnosis(plan: dict) -> DiagnosisConfig:
    """故障诊断方案 → 诊断配置"""
    cfg = plan.get("fault_diagnosis_plan", plan)
    methods = cfg.get("diagnosis_method", {})
    impact = cfg.get("impact_assessment", {})

    return DiagnosisConfig(
        methods={
            "ping": methods.get("auto_ping", True),
            "traceroute": methods.get("traceroute", True),
            "speed_test": methods.get("speed_test", False),
            "optical_check": methods.get("optical_power_check", True),
        },
        trigger={
            "min_affected_users": impact.get("affected_user_threshold", 1),
            "severity": impact.get("severity_filter", "all"),
        },
    )


def _translate_closure(plan: dict) -> ClosureConfig:
    """远程闭环方案 → 闭环配置"""
    cfg = plan.get("remote_closure_plan", plan)
    opts = cfg.get("closure_options", {})
    strategy = cfg.get("closure_strategy", {})
    audit = cfg.get("audit_strategy", {})

    return ClosureConfig(
        actions={
            "port_reset": opts.get("port_reset", False),
            "bw_adjust": opts.get("bandwidth_adjustment", False),
            "channel_switch": opts.get("channel_switch", False),
            "fw_upgrade": opts.get("firmware_upgrade", False),
        },
        policy={
            "auto": strategy.get("auto_execute", False),
            "need_approval": strategy.get("approval_required", True),
            "max_retry": strategy.get("max_retry", 3),
            "retry_interval_min": strategy.get("retry_interval_min", 10),
        },
        audit={
            "enabled": audit.get("audit_enabled", True),
            "interval_hour": audit.get("audit_interval_hour", 24),
            "rollback": audit.get("rollback_on_failure", True),
        },
    )


def _translate_optimization(plan: dict) -> OptimizationConfig:
    """动态优化方案 → 优化配置"""
    cfg = plan.get("dynamic_optimization_plan", plan)
    realtime = cfg.get("realtime_optimization", {})
    habit = cfg.get("habit_pre_optimization", {})

    return OptimizationConfig(
        realtime={
            "enabled": realtime.get("enabled", False),
            "qos_adjust": realtime.get("qos_auto_adjust", False),
            "load_balance": realtime.get("load_balancing", False),
            "congestion_ctrl": realtime.get("congestion_control", False),
        },
        prediction={
            "enabled": habit.get("enabled", False),
            "learn_days": habit.get("learning_period_days", 7),
            "pre_alloc": habit.get("pre_allocation_enabled", False),
            "pre_alloc_advance_min": habit.get("pre_allocation_advance_min", 30),
        },
    )


def validate_config(output: PipelineOutput) -> dict:
    """校验生成的配置格式合规性

    Args:
        output: PipelineOutput 对象

    Returns:
        {"passed": bool, "errors": list}
    """
    errors = []

    # 校验感知配置必填字段
    p = output.perception
    if not p.thresholds:
        errors.append("perception.thresholds 不能为空")
    if "rtt_alarm_ms" not in p.thresholds:
        errors.append("perception.thresholds.rtt_alarm_ms 缺失")

    # 校验时间格式
    for field, val in p.schedule.items():
        if not _is_valid_time(val):
            errors.append(f"perception.schedule.{field}={val} 时间格式不正确（应为 HH:MM）")

    return {"passed": len(errors) == 0, "errors": errors}


def export_config(output: PipelineOutput) -> list[str]:
    """将配置导出为 JSON 文件

    Args:
        output: PipelineOutput 对象

    Returns:
        导出的文件路径列表
    """
    output_dir = f"outputs/configs/{output.session_id}"
    os.makedirs(output_dir, exist_ok=True)

    files = []
    configs = {
        "perception_config.json": output.perception.model_dump(),
        "diagnosis_config.json": output.diagnosis.model_dump(),
        "closure_config.json": output.closure.model_dump(),
        "optimization_config.json": output.optimization.model_dump(),
    }

    for filename, data in configs.items():
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        files.append(filepath)

    return files


def _is_valid_time(t: str) -> bool:
    """校验 HH:MM 格式"""
    try:
        parts = t.split(":")
        if len(parts) != 2:
            return False
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        return False
