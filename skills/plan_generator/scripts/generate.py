#!/usr/bin/env python3
"""方案模板填充脚本"""
import asyncio
import json
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parent.parent
REFERENCES_DIR = SKILL_DIR / "references"

TEMPLATE_FILES = [
    "cei_perception.json",
    "fault_diagnosis.json",
    "remote_closure.json",
    "dynamic_optimization.json",
    "manual_fallback.json",
]


def load_template(name: str) -> dict[str, Any]:
    """加载指定方案模板"""
    path = REFERENCES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_templates() -> dict[str, dict[str, Any]]:
    """加载所有方案模板"""
    return {name: load_template(name) for name in TEMPLATE_FILES}


def load_filling_rules() -> str:
    """加载参数决策规则"""
    return (REFERENCES_DIR / "filling_rules.md").read_text(encoding="utf-8")


def _deep_get(d: dict[str, Any], path: str) -> Any:
    """按点号路径获取嵌套字典值"""
    keys = path.split(".")
    cur = d
    for k in keys:
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
    return cur


def _deep_set(d: dict[str, Any], path: str, value: Any) -> bool:
    """按点号路径设置嵌套字典值，返回是否成功"""
    keys = path.split(".")
    cur = d
    for k in keys[:-1]:
        if k not in cur:
            return False
        cur = cur[k]
    if keys[-1] in cur:
        cur[keys[-1]] = value
        return True
    return False


def fill_template(
    template: dict[str, Any],
    params: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """
    填充模板参数。

    Args:
        template: 原始模板
        params: 需要覆盖的参数（点号路径 → 新值）

    Returns:
        (填充后的模板, 修改字段列表)
    """
    filled = json.loads(json.dumps(template))  # deep copy
    changes: list[str] = []
    for path, new_value in params.items():
        old_value = _deep_get(filled, path)
        if _deep_set(filled, path, new_value):
            changes.append(f"{path}: {old_value!r} → {new_value!r}")
    return filled, changes


def build_params_from_intent(
    intent_goal: dict[str, Any],
    template_name: str,
) -> dict[str, Any]:
    """
    根据意图目标和模板名称，构建需要覆盖的参数。
    此函数实现 filling_rules.md 中的规则逻辑。
    """
    params: dict[str, Any] = {}
    user_type = intent_goal.get("user_type", "")
    sensitivity = intent_goal.get("guarantee_target", {}).get("sensitivity", "")
    priority = intent_goal.get("guarantee_target", {}).get("priority_level", "medium")
    period = intent_goal.get("guarantee_period", {})
    start_time = period.get("start_time", "00:00")
    end_time = period.get("end_time", "23:59")
    all_day = (start_time == "00:00" and end_time == "23:59")

    if template_name == "cei_perception.json":
        # 保障时段
        if not all_day:
            params["cei_perception.trigger_window.start_time"] = start_time
            params["cei_perception.trigger_window.end_time"] = end_time
            params["cei_perception.trigger_window.all_day"] = False
        # 用户类型特化
        if "直播" in user_type or "卡顿" in sensitivity:
            params["cei_perception.warning_threshold.latency_ms"] = 50
            params["cei_perception.perception_granularity.per_user_enabled"] = True
            params["cei_perception.perception_granularity.sampling_interval_sec"] = 60
        if "游戏" in user_type or "延迟" in sensitivity:
            params["cei_perception.warning_threshold.latency_ms"] = 30
            params["cei_perception.warning_threshold.jitter_ms"] = 10
        if "稳定" in sensitivity:
            params["cei_perception.warning_threshold.packet_loss_rate"] = 0.001

    elif template_name == "remote_closure.json":
        if "直播" in user_type:
            params["remote_closure.closure_strategy.auto_execute"] = True
        if priority == "high":
            params["remote_closure.closure_strategy.require_approval"] = False

    elif template_name == "dynamic_optimization.json":
        if "直播" in user_type or "游戏" in user_type:
            params["dynamic_optimization.realtime_optimization.enabled"] = True
            params["dynamic_optimization.realtime_optimization.qos_auto_adjust"] = True
        if "游戏" in user_type:
            params["dynamic_optimization.realtime_optimization.congestion_control"] = True
        if "办公" in user_type:
            params["dynamic_optimization.habit_pre_optimization.enabled"] = True

    elif template_name == "manual_fallback.json":
        if priority == "high":
            params["manual_fallback.trigger_conditions.high_priority_user"] = True
            params["manual_fallback.dispatch_policy.priority_level"] = "high"
            params["manual_fallback.dispatch_policy.expected_response_minutes"] = 15

    return params


async def fill_single_template(
    template_name: str,
    intent_goal: dict[str, Any],
) -> dict[str, Any]:
    """异步填充单个模板"""
    template = load_template(template_name)
    params = build_params_from_intent(intent_goal, template_name)
    filled, changes = fill_template(template, params)
    return {
        "plan_name": template.get("plan_name", template_name),
        "template": template_name,
        "filled_data": filled,
        "changes": changes,
        "status": "filled",
    }


async def fill_all_templates(
    intent_goal: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    并行填充所有 5 个方案模板。

    Returns:
        填充结果列表，每项包含 plan_name / filled_data / changes / status
    """
    tasks = [fill_single_template(name, intent_goal) for name in TEMPLATE_FILES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: list[dict[str, Any]] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            output.append({
                "plan_name": TEMPLATE_FILES[i],
                "template": TEMPLATE_FILES[i],
                "filled_data": {},
                "changes": [],
                "status": "failed",
                "error": str(result),
            })
        else:
            output.append(result)  # type: ignore[arg-type]
    return output


if __name__ == "__main__":
    """CLI 入口 — 供 get_skill_script(execute=True) 调用

    用法（推荐，节省 token）：
        python generate.py --intent-file outputs/<sid>/intent.json

    向后兼容用法：
        python generate.py '<intent_goal_json>'

    输出: JSON 字符串，含 plans(list) / rules(str)
    """
    import sys

    def _read_arg(flag: str, argv_pos: int, default: str = "{}") -> str:
        """先找 --flag <path>（读文件），降级到 sys.argv[pos] 内联字符串。"""
        argv = sys.argv[1:]
        if flag in argv:
            idx = argv.index(flag) + 1
            if idx < len(argv):
                return Path(argv[idx]).read_text(encoding="utf-8")
        return argv[argv_pos] if len(argv) > argv_pos else default

    intent_goal_json = _read_arg("--intent-file", 0)
    try:
        raw = json.loads(intent_goal_json)
    except json.JSONDecodeError:
        print(json.dumps({"error": "intent_goal_json 格式错误"}, ensure_ascii=False))
        sys.exit(1)

    # intent.json 完整结构为 {"complete":..., "intent_goal":{...}, "profile":{...}}
    # 兼容直接传入 intent_goal dict 的场景
    if isinstance(raw, dict) and "intent_goal" in raw:
        intent_goal = raw["intent_goal"]
    else:
        intent_goal = raw

    results = asyncio.run(fill_all_templates(intent_goal))
    rules = load_filling_rules()

    print(json.dumps(
        {"plans": results, "rules": rules[:500]},
        ensure_ascii=False,
    ))
