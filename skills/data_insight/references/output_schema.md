# 数据洞察 Skills 输出数据契约

> 供前端开发参考：每个脚本通过 stdout 输出 JSON，agno 框架将其包装在 ToolCallCompleted 事件中推送给前端。
> 前端可通过 `tool_name`（脚本名）区分不同阶段的数据。

---

## 1. list_schema.py — Schema 查询

**触发时机**：InsightAgent 在 Decompose 阶段查询天表/分钟表的可用字段

**前端用途**：可选展示，一般不需要渲染

```json
{
  "status": "ok",
  "skill": "data_insight",
  "op": "list_schema",
  "table": "day",
  "focus_dimensions": ["ODN"],
  "schema_markdown": "## 核心分组字段\n- portUuid ...",
  "all_fields": ["CEI_score", "ODN_score", ...]
}
```

---

## 2. run_query.py — 纯数据查询

**触发时机**：InsightAgent 需要拉原始数据但不做洞察分析

**前端用途**：可选，一般作为中间步骤

```json
{
  "status": "ok",
  "skill": "data_insight",
  "op": "run_query",
  "fixed_query_config": { ... },
  "fix_warnings": ["字段替换: 'xxx' → 'yyy'"],
  "data_shape": [3857, 10],
  "columns": ["portUuid", "CEI_score", ...],
  "records": [
    {"portUuid": "uuid-a", "CEI_score": 54.08, ...},
    ...
  ],
  "summary": "数据行数：3857，CEI_score：最大=100.000, 最小=54.080 ..."
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| records | array | 最多 50 条记录 |
| columns | array | 列名列表 |
| data_shape | [int, int] | [行数, 列数] |
| summary | string | 文字摘要 |

---

## 3. run_insight.py — 洞察函数执行（核心）

**触发时机**：InsightAgent 对每个分析步骤调用 12 种洞察函数之一

**前端用途**：⭐ 核心渲染对象 — 每次调用对应一个分析步骤的结果

```json
{
  "status": "ok",
  "skill": "data_insight",
  "op": "run_insight",
  "insight_type": "OutstandingMin",
  "significance": 0.73,
  "description": {
    "min_group": "288b6c71-...",
    "min_value": 54.08,
    "second_value": 55.42,
    "gap": 1.34,
    "z_score": 5.36,
    "summary": "CEI_score 最小值出现在 288b6c71-...（54.08），低于第二名 1.34，z-score=5.36"
  },
  "filter_data": [
    {"portUuid": "288b6c71-...", "CEI_score": 54.08},
    {"portUuid": "1c86d285-...", "CEI_score": 55.42},
    ...
  ],
  "chart_configs": {
    "chart_type": "bar",
    "title": {"text": "CEI_score 最小值分析 (Top10)", ...},
    "tooltip": {...},
    "grid": {...},
    "xAxis": {"type": "category", "data": [...]},
    "yAxis": {"type": "value", "name": "CEI_score"},
    "series": [{"type": "bar", "data": [...]}]
  },
  "fix_warnings": [],
  "found_entities": {
    "portUuid": ["288b6c71-...", "1c86d285-...", ...]
  },
  "data_shape": [3857, 2],
  "value_columns_used": ["CEI_score"],
  "group_column_used": "portUuid"
}
```

### 关键字段说明

| 字段 | 类型 | 前端怎么用 |
|---|---|---|
| `insight_type` | string | 标识洞察类型，可作为步骤卡片标题。12 种可选值见下表 |
| `significance` | float [0, 1] | 结果显著性。>= 0.5 高亮，< 0.3 可折叠 |
| `description` | string 或 dict | dict 时取 `.summary` 字段作为文字描述 |
| `filter_data` | array[dict] | 最多 50 条，可渲染为表格 |
| `chart_configs` | dict | **完整的 ECharts option**，前端直接传给 `echarts.setOption()` 即可 |
| `found_entities` | dict | 下钻实体，如 `{"portUuid": [...]}`，可作为关联标签展示 |
| `data_shape` | [int, int] | 查询结果的完整行列数（filter_data 是截断后的） |
| `fix_warnings` | array[string] | 三元组自动修复的警告信息 |

### 12 种 insight_type

| insight_type | chart_type | 说明 |
|---|---|---|
| OutstandingMin | bar | 找最低值 |
| OutstandingMax | bar | 找最高值 |
| OutstandingTop2 | bar | 找前两名 |
| Trend | line | 线性回归趋势 |
| ChangePoint | line + markLine | 时序变点检测 |
| Seasonality | line | 周期性检测 |
| OutlierDetection | scatter | 异常点检测 |
| Correlation | scatter | 两指标相关性 |
| CrossMeasureCorrelation | heatmap | 多指标交叉相关 |
| Clustering | scatter | KMeans 聚类 |
| Attribution | pie/bar | 贡献度归因 |
| Evenness | bar | 均匀度分析 |

---

## 4. run_nl2code.py — NL2Code 沙箱执行

**触发时机**：InsightAgent 需要自定义 pandas 分析（如 Top N 查询、多列比较）

**前端用途**：步骤结果展示（类似 run_insight 但没有 chart_configs）

```json
{
  "status": "ok",
  "skill": "data_insight",
  "op": "run_nl2code",
  "result": {
    "type": "dataframe",
    "shape": [5, 10],
    "columns": ["portUuid", "CEI_score", ...],
    "records": [
      {"portUuid": "288b6c71-...", "CEI_score": 54.08, ...}
    ]
  },
  "description": "NL2Code 分析完成 — 筛选 5 个低分 PON 口；结果 5 行 x 10 列",
  "fix_warnings": [],
  "data_shape": [3857, 10],
  "code": "target_ports = [...]\nresult = df[df['portUuid'].isin(target_ports)]..."
}
```

### result 的 type 变体

| type | 字段 | 说明 |
|---|---|---|
| `"dataframe"` | shape, columns, records | DataFrame 结果（最常见） |
| `"dict"` | value | 字典结果 |
| `"list"` | value | 列表结果 |
| `"scalar"` | text | 标量/字符串结果 |
| `"none"` | — | result 未赋值 |

---

## 5. render_report.py — 报告渲染

**触发时机**：InsightAgent 完成所有 Phase 后生成最终报告

**前端用途**：⭐ 最终报告渲染

**注意**：当前 agno 的 args 类型校验问题导致此脚本经常调用失败，InsightAgent 会兜底在 assistant 文本中直接输出 Markdown 报告。

成功时输出**纯 Markdown 文本**（不是 JSON）：
```markdown
# CEI 低分 PON 口根因分析报告

## 执行摘要
| 项目 | 内容 |
|------|------|
| 分析目标 | 找出 CEI 分数较低的 PON 口并分析原因 |
| 低分端口数量 | 10 个 |
...

## Phase 1: L1 - 低分 PON 口识别
...
```

---

## 6. 错误格式（所有脚本通用）

```json
{
  "status": "error",
  "skill": "data_insight",
  "op": "run_insight",
  "error": "错误描述信息"
}
```

前端遇到 `status: "error"` 时应展示错误提示。

---

## 7. 通过 tool_name 区分数据来源

agno 推送给前端的 ToolCallCompleted 事件中包含 `tool_name`（即 `get_skill_script`），
前端可通过事件中的 `script_path` 或 stdout JSON 的 `op` 字段区分：

| op 值 | 对应脚本 | 前端渲染方式 |
|---|---|---|
| `list_schema` | list_schema.py | 可忽略或折叠 |
| `run_query` | run_query.py | 数据表格（可折叠） |
| `run_insight` | run_insight.py | **步骤卡片 + ECharts 图表** |
| `run_nl2code` | run_nl2code.py | 数据表格 + 代码展示 |

## 8. InsightAgent 文本输出（非脚本）

除了脚本 stdout，InsightAgent 还会在 assistant 文本中输出：

### 结构化交接契约（JSON 代码块）
```json
{
  "summary": {
    "goal": "分析目标",
    "priority_pons": ["uuid-a", "uuid-b"],
    "distinct_issues": ["问题1", "问题2"],
    "scope_indicator": "single_pon" | "multi_pon" | "regional",
    "peak_time_window": "19:00-22:00" | null,
    "has_complaints": false,
    "root_cause_fields": ["rxTrafficPercent", ...],
    "reflection_log": [{"phase": 1, "choice": "A", "reason": "..."}]
  }
}
```

### 指针陈述（纯文本）
```
✅ 查询到 5 个低 CEI PON 口，主要根因为上行流量异常...
```
