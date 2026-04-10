#!/usr/bin/env python3
"""WIFI 仿真 4 步流水线 — Mock 实现。

作为 agno Skill 脚本被调用。内部按序执行：
  1. 户型图识别
  2. 热力图生成
  3. RSSI 采集
  4. 选点对比
每步产出数据 + ECharts option。
"""

import json
import random
import sys
from typing import Any, Dict, List


_SCHEMA_DEFAULTS: Dict[str, Any] = {
    "floor_plan_hint": "三室一厅",
    "area_sqm": 100,
    "wall_material": "brick",
}


def _step_1_floorplan(params: Dict[str, Any]) -> Dict[str, Any]:
    rooms = [
        {"id": "客厅", "area": 30, "x": 4, "y": 4},
        {"id": "主卧", "area": 18, "x": 1, "y": 7},
        {"id": "次卧1", "area": 12, "x": 8, "y": 7},
        {"id": "次卧2", "area": 10, "x": 8, "y": 2},
        {"id": "厨房", "area": 8, "x": 1, "y": 2},
    ]
    graph_nodes = [
        {"name": r["id"], "x": r["x"] * 50, "y": r["y"] * 50, "symbolSize": max(20, r["area"])}
        for r in rooms
    ]
    graph_links = [
        {"source": "客厅", "target": "主卧"},
        {"source": "客厅", "target": "次卧1"},
        {"source": "客厅", "target": "次卧2"},
        {"source": "客厅", "target": "厨房"},
    ]
    echarts_option = {
        "title": {"text": "户型结构识别", "left": "center"},
        "tooltip": {},
        "series": [
            {
                "type": "graph",
                "layout": "none",
                "roam": True,
                "label": {"show": True},
                "data": graph_nodes,
                "links": graph_links,
                "lineStyle": {"width": 2, "color": "#5470c6"},
            }
        ],
    }
    return {
        "step": 1,
        "name": "户型图识别",
        "status": "success",
        "result": {"rooms": rooms, "wall_material": params.get("wall_material", "brick")},
        "echarts_option": echarts_option,
    }


def _step_2_heatmap(params: Dict[str, Any]) -> Dict[str, Any]:
    random.seed(42)
    grid_x, grid_y = 10, 10
    heatmap_data: List[List[float]] = []
    for i in range(grid_x):
        for j in range(grid_y):
            # 中心强度最高，边缘衰减
            dist = ((i - 5) ** 2 + (j - 5) ** 2) ** 0.5
            rssi = -40 - dist * 3 - random.uniform(0, 5)
            heatmap_data.append([i, j, round(rssi, 1)])

    echarts_option = {
        "title": {"text": "WIFI 覆盖热力图 (当前 AP 布局)", "left": "center"},
        "tooltip": {"position": "top"},
        "grid": {"height": "60%", "top": "15%"},
        "xAxis": {"type": "category", "data": [str(i) for i in range(grid_x)]},
        "yAxis": {"type": "category", "data": [str(j) for j in range(grid_y)]},
        "visualMap": {
            "min": -90,
            "max": -40,
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "inRange": {
                "color": ["#d73027", "#fc8d59", "#fee090", "#e0f3f8", "#91bfdb", "#4575b4"]
            },
        },
        "series": [
            {
                "name": "RSSI (dBm)",
                "type": "heatmap",
                "data": heatmap_data,
                "label": {"show": False},
            }
        ],
    }
    return {
        "step": 2,
        "name": "热力图生成",
        "status": "success",
        "result": {"grid_size": [grid_x, grid_y], "min_rssi": -85, "avg_rssi": -62},
        "echarts_option": echarts_option,
    }


def _step_3_rssi(params: Dict[str, Any]) -> Dict[str, Any]:
    samples = [
        {"location": "客厅", "rssi": -48},
        {"location": "主卧", "rssi": -68},
        {"location": "次卧1", "rssi": -72},
        {"location": "次卧2", "rssi": -78},
        {"location": "厨房", "rssi": -65},
    ]
    categories = [s["location"] for s in samples]
    values = [s["rssi"] for s in samples]
    echarts_option = {
        "title": {"text": "各房间 RSSI 采样", "left": "center"},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value", "name": "RSSI (dBm)", "min": -90, "max": -30},
        "series": [
            {
                "type": "bar",
                "data": values,
                "itemStyle": {"color": "#5470c6"},
                "markLine": {"data": [{"yAxis": -70, "name": "覆盖阈值"}]},
            }
        ],
    }
    return {
        "step": 3,
        "name": "RSSI 采集",
        "status": "success",
        "result": {"rssi_samples": samples, "weak_points": ["次卧2"]},
        "echarts_option": echarts_option,
    }


def _step_4_ap_select(params: Dict[str, Any]) -> Dict[str, Any]:
    current_ap = {"position": [4, 4], "room": "客厅"}
    recommended_ap = {"position": [5, 5], "room": "走廊"}
    before = [{"location": "次卧2", "rssi": -78}, {"location": "主卧", "rssi": -68}]
    after = [{"location": "次卧2", "rssi": -71}, {"location": "主卧", "rssi": -61}]
    echarts_option = {
        "title": {"text": "选点前后 RSSI 对比", "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0, "data": ["调整前", "调整后"]},
        "xAxis": {"type": "category", "data": [b["location"] for b in before]},
        "yAxis": {"type": "value", "name": "RSSI (dBm)", "min": -90, "max": -30},
        "series": [
            {"name": "调整前", "type": "bar", "data": [b["rssi"] for b in before], "itemStyle": {"color": "#ee6666"}},
            {"name": "调整后", "type": "bar", "data": [a["rssi"] for a in after], "itemStyle": {"color": "#91cc75"}},
        ],
    }
    return {
        "step": 4,
        "name": "选点对比",
        "status": "success",
        "result": {
            "current_ap": current_ap,
            "recommended_ap": recommended_ap,
            "improvement_dbm": 7,
            "before": before,
            "after": after,
        },
        "echarts_option": echarts_option,
    }


def simulate(params_json: str = "{}") -> str:
    """执行 WIFI 仿真 4 步流水线。"""
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "参数 JSON 解析失败"}, ensure_ascii=False)
    merged = {**_SCHEMA_DEFAULTS, **params}

    steps = [
        _step_1_floorplan(merged),
        _step_2_heatmap(merged),
        _step_3_rssi(merged),
        _step_4_ap_select(merged),
    ]

    result = {
        "skill": "wifi_simulation",
        "params": merged,
        "steps": steps,
        "summary": "建议将主 AP 从客厅迁移至走廊，次卧2 覆盖改善约 7 dBm",
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    _params = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(simulate(_params))
