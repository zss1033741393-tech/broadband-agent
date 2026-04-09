#!/usr/bin/env python3
"""方案评审 — Mock 约束校验。

原型阶段：随机返回 3 种结果之一（全通过 / 带警告 / 未通过）。
未通过时必须同时返回 violations 与 recommendations 列表。
"""

import json
import random
import sys
from typing import Any, Dict, List


_CHECK_DIMENSIONS = [
    ("组网兼容性检查", "network_topology"),
    ("性能冲突检测", "performance_conflict"),
    ("SLA 合规检查", "sla_compliance"),
    ("资源容量检查", "resource_capacity"),
]


def _scenario_all_pass() -> Dict[str, Any]:
    return {
        "passed": True,
        "violations": [],
        "recommendations": [],
        "checks": [
            {"name": name, "dimension": dim, "result": "pass"}
            for name, dim in _CHECK_DIMENSIONS
        ],
    }


def _scenario_pass_with_warnings() -> Dict[str, Any]:
    return {
        "passed": True,
        "violations": [
            {
                "dimension": "performance_conflict",
                "severity": "warning",
                "message": "时段 18:00-22:00 与现有高优先级策略（视频VIP保障）有重叠",
                "affected_section": "CEI 配置方案",
            },
            {
                "dimension": "resource_capacity",
                "severity": "warning",
                "message": "目标 PON 口当前负载率较高（87%），建议关注",
                "affected_section": "差异化承载方案",
            },
        ],
        "recommendations": [
            {
                "target_section": "CEI 配置方案",
                "suggested_change": "调整采集时段为 19:00-23:00，错开现有 VIP 策略",
                "reason": "避免优先级冲突导致 CEI 采集被抑制",
            },
        ],
        "checks": [
            {"name": "组网兼容性检查", "dimension": "network_topology", "result": "pass"},
            {"name": "性能冲突检测", "dimension": "performance_conflict", "result": "warn"},
            {"name": "SLA 合规检查", "dimension": "sla_compliance", "result": "pass"},
            {"name": "资源容量检查", "dimension": "resource_capacity", "result": "warn"},
        ],
    }


def _scenario_fail() -> Dict[str, Any]:
    return {
        "passed": False,
        "violations": [
            {
                "dimension": "sla_compliance",
                "severity": "error",
                "message": "CEI 阈值超出当前套餐 SLA 保障上限（套餐承诺 70 分）",
                "affected_section": "CEI 配置方案",
            },
            {
                "dimension": "performance_conflict",
                "severity": "error",
                "message": "CEI 粒度 minute 在直播时段与现有分钟级采集任务冲突",
                "affected_section": "CEI 配置方案",
            },
        ],
        "recommendations": [
            {
                "target_section": "CEI 配置方案",
                "suggested_change": "将 CEI 阈值从当前值降到 70 以满足 SLA 约束",
                "reason": "当前套餐 SLA 承诺 70 分体验保障，设置更高阈值为超配",
            },
            {
                "target_section": "CEI 配置方案",
                "suggested_change": "调整 CEI 粒度为 hour，或调整采集时段避开现有分钟级任务窗口",
                "reason": "同一 PON 口无法同时运行多个分钟级 CEI 采集任务",
            },
        ],
        "checks": [
            {"name": "组网兼容性检查", "dimension": "network_topology", "result": "pass"},
            {"name": "性能冲突检测", "dimension": "performance_conflict", "result": "fail"},
            {"name": "SLA 合规检查", "dimension": "sla_compliance", "result": "fail"},
            {"name": "资源容量检查", "dimension": "resource_capacity", "result": "pass"},
        ],
    }


def review(plan_markdown: str = "") -> str:
    """执行 mock 约束检查。

    Args:
        plan_markdown: plan_design 产出的分段方案 Markdown 字符串（当前 mock 不使用）

    Returns:
        校验结果 JSON
    """
    # [原型阶段] 随机选一个场景；接入真实系统后改为真实检查
    scenario = random.choice([
        _scenario_all_pass,
        _scenario_pass_with_warnings,
        _scenario_fail,
    ])
    return json.dumps(scenario(), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    plan = sys.argv[1] if len(sys.argv) > 1 else ""
    print(review(plan))
