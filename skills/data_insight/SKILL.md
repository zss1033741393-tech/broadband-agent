---
name: data_insight
description: "数据洞察：按阶段查询网络质量数据 + 归因分析，输出数据 + 分析文本 + ECharts 可视化配置"
---

# 数据洞察

## Metadata
- **paradigm**: Pipeline + Tool-augmented
- **when_to_use**: InsightAgent 需要进行网络质量数据查询或归因分析
- **inputs**: 阶段标识（`stage`）+ 可选过滤条件（`query_type`）
- **outputs**: `{data, analysis, echarts_option, stage, summary}` JSON

## 阶段契约（4 阶段对应 4 种调用）

| 阶段 | `stage` 值 | 产出 ECharts 图类型 | 说明 |
|---|---|---|---|
| 1. 需求理解 | `intent` | — | 不调用本脚本，InsightAgent LLM 自行判断 |
| 2. 数据查询 | `query` | 柱状图（按 PON 口 CEI 排名）+ 线图（时序趋势） | 返回原始数据 + echarts_option |
| 3. 归因分析 | `attribution` | 热力图（PON 口问题分布）+ 雷达图（异常指标） | 返回归因结果 + echarts_option |
| 4. 报告生成 | — | — | 调用 `report_rendering` Skill，不调用本 Skill |

## Output Schema

```json
{
  "skill": "data_insight",
  "stage": "query" | "attribution",
  "data": [...],                    // 原始数据（stage=query 时）
  "analysis": [...],                // 归因分析（stage=attribution 时）
  "echarts_option": { ... },        // ECharts option JSON,直接可渲染
  "summary": {
    "priority_pons": [...],
    "distinct_issues": [...],
    "scope_indicator": "single_pon" | "multi_pon" | "regional",
    "peak_time_window": "19:00-22:00" | null,
    "has_complaints": true,
    "remote_loop_candidates": [...]
  }
}
```

**关键字段**：
- `echarts_option` — 完整的 ECharts option 对象，Agent 透传给前端即可渲染；**不得改写**
- `summary` — 结构化摘要，供 Orchestrator 在洞察回流 Planning 时作为 hints 注入

## When to Use

- ✅ 用户要求查询 PON 口排名 / 分析 CEI 分布 / 找异常原因
- ✅ 区域性保障的第一步（场景 2）
- ❌ 用户要求生成配置（应走 Planning/Provisioning 路径）
- ❌ 单点功能（场景 3）

## How to Use

### 阶段 2 — 数据查询
```
get_skill_script(
    "data_insight",
    "mock_query.py",
    execute=True,
    args=["query", "<query_type>"]
)
```
`query_type` ∈ `{all, low_cei, high_util}`（可选，默认 `all`）

### 阶段 3 — 归因分析
```
get_skill_script(
    "data_insight",
    "mock_query.py",
    execute=True,
    args=["attribution"]
)
```

## Scripts

- `scripts/mock_query.py` — Mock 数据查询与归因分析，按 `stage` 参数产出不同 ECharts 配置

## Examples

**查询阶段返回**（简化）:
```json
{
  "skill": "data_insight",
  "stage": "query",
  "data": [
    {"pon_port": "PON-2/0/5", "cei_score": 48.9, ...}
  ],
  "echarts_option": {
    "title": {"text": "PON 口 CEI 评分排名"},
    "xAxis": {"type": "category", "data": ["PON-2/0/5", ...]},
    "yAxis": {"type": "value"},
    "series": [{"type": "bar", "data": [48.9, ...]}]
  },
  "summary": { ... }
}
```

## 禁止事项

- ❌ 不在本 Skill 里做方案推荐（方案归 PlanningAgent）
- ❌ 不得改写或精简 echarts_option（前端直接渲染）
