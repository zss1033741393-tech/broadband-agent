---
name: data_insight
description: "数据洞察执行层：三元组查询 + 12 种洞察函数 + NL2Code 沙箱 + 天表/分钟表 Schema 查询"
---

# 数据洞察

## Metadata
- **paradigm**: Pipeline + Tool Wrapper
- **when_to_use**: InsightAgent 在 plan / decompose / execute 阶段驱动数据查询与分析
- **inputs**: 单步 payload（三元组 + insight_type 或 NL2Code 代码）
- **outputs**: 结构化 JSON（含 filter_data / significance / description / chart_configs）

## When to Use

- ✅ InsightAgent 按 Phase 分解出一个 Step，需要拉数据 / 跑洞察 / 执行 NL2Code
- ✅ InsightAgent 在 decompose 前需要查询天表 / 分钟表的合法字段
- ❌ 方案设计 / 方案评审（归 PlanningAgent）
- ❌ 综合目标的 Provisioning 执行（归 3 个 Provisioning Agent）
- ❌ 在本 Skill 里做业务规则判断 —— Skill **只做确定性计算与调用**，LLM 决策全部归 InsightAgent

## 范式说明

本 Skill 是 `ce_insight_core` Python 包的轻量包装：

- **Tool Wrapper**：把 `ce_insight_core` 的 `query_subject_pandas` / `run_insight` / `fix_query_config` / `sandbox.run_nl2code` / schema 管理器封装成 4 个 CLI 入口
- **Pipeline**：InsightAgent 驱动 plan → phase 循环 → step 循环 → reflect → report；每个 step 对应一次 Skill 脚本调用

## How to Use

### Step 1 — 获取 SKILL.md 指令（强制）
```
get_skill_instructions("data_insight")
```

### Step 2 — 查询 Schema（规划 / 分解阶段）
了解可用字段、维度剪枝后的 schema：
```
get_skill_script(
    "data_insight",
    "list_schema.py",
    execute=True,
    args=["<payload_json_string>"]
)
```
payload：
```json
{"table": "day", "focus_dimensions": ["ODN"]}
```
`focus_dimensions` 可选；为 `[]` 或缺省时返回全量 schema。

### Step 3 — 三元组数据查询
仅拉数据，不做分析：
```
get_skill_script(
    "data_insight",
    "run_query.py",
    execute=True,
    args=["<payload_json_string>"]
)
```
payload：
```json
{
  "query_config": {
    "dimensions": [[]],
    "breakdown": {"name": "portUuid", "type": "UNORDERED"},
    "measures": [{"name": "CEI_score", "aggr": "AVG"}]
  },
  "table_level": "day"
}
```

### Step 4 — 洞察函数执行（推荐路径）
拉数据 + 跑指定洞察函数：
```
get_skill_script(
    "data_insight",
    "run_insight.py",
    execute=True,
    args=["<payload_json_string>"]
)
```
payload：
```json
{
  "insight_type": "OutstandingMin",
  "query_config": { ... 三元组 ... },
  "table_level": "day",
  "value_columns": ["CEI_score"],
  "group_column": "portUuid"
}
```
`value_columns` / `group_column` 可省略，会从 `query_config.measures` / `breakdown` 推导。

返回 JSON 中的 `chart_configs` 是完整 ECharts option，**原样透传**，严禁改写。
`found_entities` 含该步骤提取的维度值，供后续 step 做 `IN` 过滤下钻。

### Step 5 — NL2Code 沙箱执行
拉数据 + 执行 **InsightAgent 直接写的** pandas 代码：
```
get_skill_script(
    "data_insight",
    "run_nl2code.py",
    execute=True,
    args=["<payload_json_string>"]
)
```
payload：
```json
{
  "code": "result = df.nsmallest(3, 'CEI_score')",
  "query_config": { ... 三元组 ... },
  "table_level": "day",
  "code_prompt": "取 CEI 最低的前 3 个 PON 口"
}
```

**代码约束见 `references/nl2code_spec.md`**。禁止 `import` / `open` / `exec` / 魔术属性 /
三引号字符串。结果必须赋值给 `result` 变量。

## Scripts

- `scripts/list_schema.py` — 查询天表 / 分钟表 Schema（按 focus_dimensions 剪枝）
- `scripts/run_query.py` — 纯三元组查询（修复 + 查数 + 摘要，不做分析）
- `scripts/run_insight.py` — 三元组查询 + 调用 `ce_insight_core.run_insight` 分派到 12 种洞察
- `scripts/run_nl2code.py` — 三元组查询 + 沙箱执行 InsightAgent 传入的 pandas 代码

## References

- `references/insight_catalog.md` — 12 种洞察函数 + NL2Code 兜底的触发规则与 measures 约束
- `references/triple_schema.md` — 三元组 `dimensions / breakdown / measures` 契约 + 硬约束
- `references/plan_fewshots.md` — 宏观计划设计规则 + L1→L2→L3→L4 四层下钻 + 3 条典型故事线
- `references/decompose_fewshots.md` — Phase 拆分步骤数规则 + Layer 3 根因 fewshot + 下钻筛选规则
- `references/reflect_rubric.md` — Phase 结束后 A/B/C/D 反思决策规则 + JSON 输出格式
- `references/nl2code_spec.md` — NL2Code 沙箱规范、代码约束、正确 / 错误示例、结果序列化契约

InsightAgent 按需加载：规划阶段读 `plan_fewshots.md`；分解阶段读 `decompose_fewshots.md`
+ `insight_catalog.md` + `triple_schema.md`；NL2Code 生成前读 `nl2code_spec.md`；
反思阶段读 `reflect_rubric.md`。

## Examples

### OutstandingMin 定位 CEI 最低 PON 口

调用：
```
get_skill_script("data_insight", "run_insight.py", execute=True, args=['{"insight_type":"OutstandingMin","query_config":{"dimensions":[[]],"breakdown":{"name":"portUuid","type":"UNORDERED"},"measures":[{"name":"CEI_score","aggr":"AVG"}]},"table_level":"day"}'])
```

简化返回：
```json
{
  "status": "ok",
  "skill": "data_insight",
  "op": "run_insight",
  "insight_type": "OutstandingMin",
  "significance": 0.41,
  "description": {"min_group": "p3", "summary": "..."},
  "filter_data": [{"portUuid": "p3", "CEI_score": 45.0}, ...],
  "chart_configs": {"chart_type": "bar", "series": [...]},
  "found_entities": {"portUuid": ["p3", "p2", "p1", "p4"]},
  "data_shape": [4, 2]
}
```

## 禁止事项

- ❌ 脚本内禁止调用 LLM（LLM 决策全部上移到 InsightAgent）
- ❌ 不得改写 `chart_configs`（前端直接渲染 ECharts option）
- ❌ 不得改写 `filter_data` / `found_entities` / `description` —— 必须原样透传给 InsightAgent
- ❌ 不得在 Skill 里做业务规则判断（如"套餐 X 默认阈值 70"）
- ❌ 不得在 NL2Code 沙箱里放任 `import` / `open` / `exec` —— 安全由 `ce_insight_core.sandbox` 保证
- ❌ 不得跳过 `get_skill_instructions` 直接猜参数（Skill 调用顺序是强制的）
