#!/usr/bin/env python3
"""Mock 数据查询脚本 — 模拟网络质量数据查询。"""

import json
import sys
from typing import Any, Dict, List


_MOCK_DATA = {
    "pon_stats": [
        {
            "pon_port": "PON-1/0/1",
            "olt_name": "OLT-东区-01",
            "cei_score": 62.5,
            "user_count": 48,
            "bandwidth_util": 0.87,
            "packet_loss": 0.032,
            "avg_latency_ms": 45,
            "peak_hour_util": 0.95,
            "complaint_count_7d": 5,
        },
        {
            "pon_port": "PON-1/0/3",
            "olt_name": "OLT-东区-01",
            "cei_score": 55.2,
            "user_count": 52,
            "bandwidth_util": 0.93,
            "packet_loss": 0.048,
            "avg_latency_ms": 68,
            "peak_hour_util": 0.98,
            "complaint_count_7d": 8,
        },
        {
            "pon_port": "PON-2/0/2",
            "olt_name": "OLT-西区-02",
            "cei_score": 71.8,
            "user_count": 35,
            "bandwidth_util": 0.72,
            "packet_loss": 0.015,
            "avg_latency_ms": 28,
            "peak_hour_util": 0.82,
            "complaint_count_7d": 2,
        },
        {
            "pon_port": "PON-2/0/5",
            "olt_name": "OLT-西区-02",
            "cei_score": 48.9,
            "user_count": 60,
            "bandwidth_util": 0.95,
            "packet_loss": 0.055,
            "avg_latency_ms": 85,
            "peak_hour_util": 0.99,
            "complaint_count_7d": 12,
        },
        {
            "pon_port": "PON-3/0/1",
            "olt_name": "OLT-南区-03",
            "cei_score": 82.1,
            "user_count": 28,
            "bandwidth_util": 0.55,
            "packet_loss": 0.008,
            "avg_latency_ms": 18,
            "peak_hour_util": 0.65,
            "complaint_count_7d": 0,
        },
        {
            "pon_port": "PON-3/0/4",
            "olt_name": "OLT-南区-03",
            "cei_score": 76.3,
            "user_count": 42,
            "bandwidth_util": 0.68,
            "packet_loss": 0.012,
            "avg_latency_ms": 25,
            "peak_hour_util": 0.78,
            "complaint_count_7d": 1,
        },
    ],
    "summary": {
        "total_pon_ports": 6,
        "avg_cei_score": 66.1,
        "critical_ports": 2,
        "warning_ports": 1,
        "healthy_ports": 3,
    },
}


def _analyze(data: List[Dict]) -> List[Dict]:
    """简单规则归因分析。"""
    analysis = []
    for port in data:
        issues = []
        causes = []

        if port["bandwidth_util"] > 0.90:
            issues.append("带宽利用率过高")
            causes.append(f"用户数({port['user_count']})较多，带宽竞争激烈")

        if port["packet_loss"] > 0.03:
            issues.append("丢包率超标")
            causes.append("可能存在光路衰减或设备故障")

        if port["avg_latency_ms"] > 50:
            issues.append("平均时延过高")
            causes.append("拥塞导致排队时延增加")

        if port["peak_hour_util"] > 0.95:
            issues.append("高峰期资源耗尽")
            causes.append("晚高峰流量集中，建议分流或扩容")

        if port["complaint_count_7d"] > 3:
            issues.append(f"近7天投诉 {port['complaint_count_7d']} 次")

        analysis.append({
            "pon_port": port["pon_port"],
            "cei_score": port["cei_score"],
            "issues": issues,
            "probable_causes": causes,
            "recommendation": "建议优先关注" if port["cei_score"] < 60 else "建议持续监控" if port["cei_score"] < 75 else "状态良好",
        })

    return analysis


def query(query_type: str = "all") -> str:
    """查询网络数据。

    Args:
        query_type: 查询类型 (all | low_cei | high_util)

    Returns:
        查询结果 JSON
    """
    data = _MOCK_DATA["pon_stats"]

    if query_type == "low_cei":
        data = sorted(data, key=lambda x: x["cei_score"])
    elif query_type == "high_util":
        data = sorted(data, key=lambda x: x["bandwidth_util"], reverse=True)

    analysis = _analyze(data)

    result = {
        "query_type": query_type,
        "data": data,
        "analysis": analysis,
        "summary": _MOCK_DATA["summary"],
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    qt = sys.argv[1] if len(sys.argv) > 1 else "all"
    print(query(qt))
