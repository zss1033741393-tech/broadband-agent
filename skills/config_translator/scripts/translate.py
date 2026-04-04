#!/usr/bin/env python3
"""NL2JSON 配置转译脚本 — 将语义方案转为设备配置格式"""
import json
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parent.parent
REFERENCES_DIR = SKILL_DIR / "references"

# 语义字段路径 → 设备字段名映射
FIELD_MAPPINGS: dict[str, dict[str, str]] = {
    "perception": {
        "cei_perception.warning_threshold.latency_ms": "cei_warn_latency_threshold",
        "cei_perception.warning_threshold.packet_loss_rate": "cei_warn_loss_threshold",
        "cei_perception.warning_threshold.jitter_ms": "cei_warn_jitter_threshold",
        "cei_perception.perception_granularity.sampling_interval_sec": "cei_collect_interval",
        "cei_perception.perception_granularity.per_user_enabled": "cei_per_user_mode",
        "cei_perception.trigger_window.start_time": "cei_trigger_start",
        "cei_perception.trigger_window.end_time": "cei_trigger_end",
    },
    "closure": {
        "remote_closure.closure_strategy.auto_execute": "closure_auto_exec",
        "remote_closure.closure_strategy.require_approval": "closure_need_approval",
        "remote_closure.sensitivity_guard.block_during_guarantee_period": "closure_block_in_guarantee",
    },
    "optimization": {
        "dynamic_optimization.realtime_optimization.enabled": "opt_realtime_enable",
        "dynamic_optimization.realtime_optimization.qos_auto_adjust": "opt_qos_auto",
        "dynamic_optimization.realtime_optimization.congestion_control": "opt_congestion_ctrl",
        "dynamic_optimization.energy_saving.enabled": "opt_energy_save_enable",
        "dynamic_optimization.energy_saving.trigger_time": "opt_energy_save_start",
        "dynamic_optimization.energy_saving.resume_time": "opt_energy_save_end",
    },
}


def _deep_get(d: dict[str, Any], path: str) -> Any:
    """按点号路径获取嵌套字典值"""
    keys = path.split(".")
    cur: Any = d
    for k in keys:
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
    return cur


def translate_plan_to_config(
    plan_data: dict[str, Any],
    config_type: str,
    device_id: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """
    将单个方案数据转译为设备配置格式。

    Args:
        plan_data: 填充后的方案数据（plan 的 filled_data 字段）
        config_type: perception / closure / optimization / diagnosis
        device_id: 目标设备 ID

    Returns:
        (设备配置 dict, 转译失败的字段列表)
    """
    mapping = FIELD_MAPPINGS.get(config_type, {})
    config_data: dict[str, Any] = {}
    failed_fields: list[str] = []

    for semantic_path, device_field in mapping.items():
        value = _deep_get(plan_data, semantic_path)
        if value is None:
            failed_fields.append(semantic_path)
        else:
            config_data[device_field] = value

    device_config = {
        "config_type": config_type,
        "version": "1.0",
        "device_id": device_id,
        "config_data": config_data,
        "apply_time": "immediate",
    }
    return device_config, failed_fields


def translate_all_plans(
    plans: dict[str, Any],
    device_id: str = "",
) -> dict[str, Any]:
    """
    将所有方案转译为 4 类设备配置。

    Args:
        plans: 填充后的方案字典，key 为模板文件名
        device_id: 目标设备 ID

    Returns:
        {configs: [...], success: bool, failed_fields: [...]}
    """
    plan_to_config_type = {
        "cei_perception.json": "perception",
        "remote_closure.json": "closure",
        "dynamic_optimization.json": "optimization",
        "fault_diagnosis.json": "diagnosis",
    }

    configs: list[dict[str, Any]] = []
    all_failed: list[str] = []

    for plan_name, config_type in plan_to_config_type.items():
        plan = plans.get(plan_name, {})
        filled_data = plan.get("filled_data", {})

        if config_type == "diagnosis":
            # 诊断配置直接透传，格式已兼容设备
            configs.append({
                "config_type": "diagnosis",
                "version": "1.0",
                "device_id": device_id,
                "config_data": filled_data.get("fault_diagnosis", {}),
                "apply_time": "immediate",
            })
        else:
            config, failed = translate_plan_to_config(filled_data, config_type, device_id)
            configs.append(config)
            all_failed.extend(failed)

    return {
        "configs": configs,
        "success": len(all_failed) == 0,
        "failed_fields": all_failed,
    }


def load_config_schema() -> dict[str, Any]:
    """加载设备配置 JSON Schema"""
    return json.loads((REFERENCES_DIR / "config_schema.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    """CLI 入口 — 供 get_skill_script(execute=True) 调用

    用法（推荐，节省 token）：
        python translate.py --plans-file outputs/<sid>/plans.json [--device-id <id>]

    向后兼容用法：
        python translate.py '<plans_json>' ['<device_id>']

    输出: JSON 字符串，含 configs / success / failed_fields / schema
    """
    import sys

    def _read_arg(flag: str, argv_pos: int, default: str = "") -> str:
        """先找 --flag <path>（读文件），降级到 sys.argv[pos] 内联字符串。"""
        argv = sys.argv[1:]
        if flag in argv:
            idx = argv.index(flag) + 1
            if idx < len(argv):
                return Path(argv[idx]).read_text(encoding="utf-8")
        return argv[argv_pos] if len(argv) > argv_pos else default

    def _read_value(flag: str, argv_pos: int, default: str = "") -> str:
        """读取普通值参数（不读文件）。"""
        argv = sys.argv[1:]
        if flag in argv:
            idx = argv.index(flag) + 1
            if idx < len(argv):
                return argv[idx]
        return argv[argv_pos] if len(argv) > argv_pos else default

    plans_json = _read_arg("--plans-file", 0, default="{}")
    device_id = _read_value("--device-id", 1, default="")

    try:
        plans = json.loads(plans_json)
    except json.JSONDecodeError:
        print(json.dumps({"error": "plans_json 格式错误"}, ensure_ascii=False))
        sys.exit(1)

    result = translate_all_plans(plans, device_id)
    schema = load_config_schema()
    result["schema"] = schema

    print(json.dumps(result, ensure_ascii=False))
