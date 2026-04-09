#!/usr/bin/env python3
"""Mock 数据查询与归因分析 — 按阶段产出 ECharts 配置。

作为 agno Skill 脚本被调用。支持两个阶段：
  query       — 返回 PON 口原始数据 + 柱状图 echarts_option
  attribution — 返回归因分析 + 雷达图 echarts_option
"""

import json
import sys
from typing import Any, Dict, List


_MOCK_DATA: List[Dict[str, Any]] = [
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
]


def _analyze(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    analysis: List[Dict[str, Any]] = []
    for port in data:
        issues: List[str] = []
        causes: List[str] = []

        if port["bandwidth_util"] > 0.90:
            issues.append("带宽利用率过高")
            causes.append(f"用户数 {port['user_count']} 较多，带宽竞争激烈")
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
            issues.append(f"近 7 天投诉 {port['complaint_count_7d']} 次")

        analysis.append(
            {
                "pon_port": port["pon_port"],
                "cei_score": port["cei_score"],
                "issues": issues,
                "probable_causes": causes,
                "recommendation": (
                    "建议优先关注"
                    if port["cei_score"] < 60
                    else "建议持续监控"
                    if port["cei_score"] < 75
                    else "状态良好"
                ),
            }
        )
    return analysis


def _build_summary(data: List[Dict[str, Any]], analysis: List[Dict[str, Any]]) -> Dict[str, Any]:
    priority_pons = [a["pon_port"] for a in analysis if a["cei_score"] < 60]
    watch_pons = [a["pon_port"] for a in analysis if 60 <= a["cei_score"] < 75]

    all_issues: List[str] = []
    for a in analysis:
        all_issues.extend(a["issues"])
    distinct_issues = list(dict.fromkeys(all_issues))

    affected = len([p for p in data if p["cei_score"] < 75])
    total = len(data) or 1
    if affected >= total * 0.5:
        scope_indicator = "regional"
    elif affected > 1:
        scope_indicator = "multi_pon"
    else:
        scope_indicator = "single_pon"

    total_complaints = sum(p.get("complaint_count_7d", 0) for p in data)
    has_peak_congestion = any(p["peak_hour_util"] > 0.95 for p in data)

    remote_loop_candidates = [
        a["pon_port"]
        for a in analysis
        if a["cei_score"] < 60
        and next(
            (p for p in data if p["pon_port"] == a["pon_port"]), {}
        ).get("complaint_count_7d", 0)
        > 3
    ]

    return {
        "priority_pons": priority_pons,
        "watch_pons": watch_pons,
        "distinct_issues": distinct_issues,
        "scope_indicator": scope_indicator,
        "has_complaints": total_complaints > 0,
        "total_complaints_7d": total_complaints,
        "peak_time_window": "19:00-22:00" if has_peak_congestion else None,
        "remote_loop_candidates": remote_loop_candidates,
    }


def _echarts_ranking(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """阶段 2 — 按 CEI 排名的柱状图。"""
    sorted_data = sorted(data, key=lambda x: x["cei_score"])
    categories = [d["pon_port"] for d in sorted_data]
    values = [d["cei_score"] for d in sorted_data]
    return {
        "title": {"text": "PON 口 CEI 评分排名", "left": "center"},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": categories, "axisLabel": {"rotate": 30}},
        "yAxis": {"type": "value", "name": "CEI 分数", "min": 0, "max": 100},
        "series": [
            {
                "name": "CEI 评分",
                "type": "bar",
                "data": values,
                "itemStyle": {
                    "color": {
                        "type": "linear",
                        "x": 0,
                        "y": 0,
                        "x2": 0,
                        "y2": 1,
                        "colorStops": [
                            {"offset": 0, "color": "#ee6666"},
                            {"offset": 1, "color": "#5470c6"},
                        ],
                    }
                },
                "markLine": {
                    "data": [
                        {"yAxis": 75, "name": "健康线"},
                        {"yAxis": 60, "name": "告警线"},
                    ]
                },
            }
        ],
    }


def _echarts_radar(analysis: List[Dict[str, Any]], data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """阶段 3 — 异常指标雷达图（取 CEI 最低的 3 个 PON 口）。"""
    low_ports = sorted(data, key=lambda x: x["cei_score"])[:3]
    indicator = [
        {"name": "带宽利用率", "max": 1.0},
        {"name": "丢包率 (×100)", "max": 10.0},
        {"name": "平均时延 (ms)", "max": 100.0},
        {"name": "高峰利用率", "max": 1.0},
        {"name": "投诉数", "max": 15.0},
    ]
    series_data = [
        {
            "value": [
                p["bandwidth_util"],
                p["packet_loss"] * 100,
                p["avg_latency_ms"],
                p["peak_hour_util"],
                p["complaint_count_7d"],
            ],
            "name": p["pon_port"],
        }
        for p in low_ports
    ]
    return {
        "title": {"text": "问题 PON 口异常指标雷达", "left": "center"},
        "tooltip": {"trigger": "item"},
        "legend": {"bottom": 0, "data": [p["pon_port"] for p in low_ports]},
        "radar": {"indicator": indicator},
        "series": [{"type": "radar", "data": series_data}],
    }


def query(stage: str = "query", query_type: str = "all") -> str:
    """按阶段产出数据 + ECharts 配置。"""
    data = _MOCK_DATA
    if query_type == "low_cei":
        data = sorted(data, key=lambda x: x["cei_score"])
    elif query_type == "high_util":
        data = sorted(data, key=lambda x: x["bandwidth_util"], reverse=True)

    analysis = _analyze(data)
    summary = _build_summary(data, analysis)

    if stage == "attribution":
        result = {
            "skill": "data_insight",
            "stage": "attribution",
            "analysis": analysis,
            "echarts_option": _echarts_radar(analysis, data),
            "summary": summary,
        }
    else:
        result = {
            "skill": "data_insight",
            "stage": "query",
            "data": data,
            "echarts_option": _echarts_ranking(data),
            "summary": summary,
        }

    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    _stage = sys.argv[1] if len(sys.argv) > 1 else "query"
    _qt = sys.argv[2] if len(sys.argv) > 2 else "all"
    print(query(_stage, _qt))
