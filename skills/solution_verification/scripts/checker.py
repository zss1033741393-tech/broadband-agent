"""Mock 约束校验脚本。

模拟组网兼容性、性能冲突和 SLA 合规性检查。
"""

import json
import random
import sys


def check(solution_json: str = "{}") -> str:
    """执行 mock 约束检查。

    Args:
        solution_json: 方案配置 JSON

    Returns:
        校验结果 JSON
    """
    # mock 实现：随机返回不同结果
    scenarios = [
        {
            "passed": True,
            "message": "所有约束校验通过",
            "warnings": [],
            "errors": [],
            "checks": [
                {"name": "组网兼容性检查", "result": "pass"},
                {"name": "性能冲突检测", "result": "pass"},
                {"name": "SLA 合规检查", "result": "pass"},
                {"name": "资源容量检查", "result": "pass"},
            ],
        },
        {
            "passed": True,
            "message": "约束校验通过，但存在警告",
            "warnings": [
                "时段 18:00-22:00 与现有高优先级策略有重叠，请确认优先级",
                "目标 PON 口当前负载率较高(87%)，建议关注",
            ],
            "errors": [],
            "checks": [
                {"name": "组网兼容性检查", "result": "pass"},
                {"name": "性能冲突检测", "result": "warning"},
                {"name": "SLA 合规检查", "result": "pass"},
                {"name": "资源容量检查", "result": "warning"},
            ],
        },
        {
            "passed": False,
            "message": "约束校验未通过",
            "warnings": [],
            "errors": [
                "CEI 采集间隔(60s)低于设备最小支持间隔(120s)",
                "保障时段超出当前 SLA 协议范围",
            ],
            "checks": [
                {"name": "组网兼容性检查", "result": "pass"},
                {"name": "性能冲突检测", "result": "fail"},
                {"name": "SLA 合规检查", "result": "fail"},
                {"name": "资源容量检查", "result": "pass"},
            ],
        },
    ]

    result = random.choice(scenarios)
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    solution = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(check(solution))
