---
name: plan_generator
description: >
  【Generator 模式】基于意图目标填充五大方案 JSON 模板。
  触发条件：IntentGoal 已完整且画像补全后；或收到约束 suggestions 需重新生成方案。
  输出五个可执行方案，供 constraint_checker 校验。
---

# 方案模板填充

## 执行步骤

**步骤 1**：加载参数决策规则（决定哪些参数需要调整）：

```
get_skill_reference("plan_generator", "filling_rules.md")
```

**步骤 2**：获取意图产出文件路径，执行方案填充：

```
# 获取上一阶段产出路径（避免内联完整 JSON 浪费 token）
get_pipeline_file("intent")   # → "outputs/<sid>/intent.json"

get_skill_script(
    "plan_generator",
    "generate.py",
    execute=True,
    args=["--intent-file", "outputs/<sid>/intent.json"]
)
```

**脚本输出**：

```json
{
  "plans": [
    {
      "plan_name": "CEI 感知方案",
      "template": "cei_perception.json",
      "filled_data": { ... },
      "changes": ["cei_perception.warning_threshold.latency_ms: 100 → 50"],
      "status": "filled"
    }
  ]
}
```

- `plans` 包含 5 项，对应五大方案模板
- `changes` 列出相对默认值的修改项，向用户展示摘要

## 规则
- 未被意图目标影响的参数保持模板默认值
- 脚本内部并行处理 5 个模板（asyncio.gather）
- 如收到约束 suggestions，按建议调整参数后重新生成，无需等待用户确认
- 可参考 domain_expert 的 CEI 指标阈值（get_skill_reference("domain_expert", "cei_metrics.md")）辅助决策参数合理性

## 后续建议
填充完成后 → 立即调用 constraint_checker 校验（必须执行）
