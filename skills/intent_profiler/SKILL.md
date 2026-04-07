---
name: intent_profiler
description: >
  【Inversion 模式】从用户自然语言中提取结构化意图，校验完整性后返回结果。
  触发条件：用户描述保障需求、优化目标时（首次输入或补充修改）。
  意图层级：用户类型（主播/游戏/VVIP）→ 套餐类型 → 业务场景 → 保障对象 → 保障时段 → 投诉记录。
  校验内容：必填字段、枚举合法性、套餐与场景组合一致性、保障时段完整性。
---

# 意图解析与画像补全

## 执行步骤

**步骤 1**：将已提取的意图字段传入工具进行校验：

```
analyze_intent(intent_goal={...})   # 首次传已知字段，未知字段留空
```

工具内部执行：结构校验 → 枚举校验 → 套餐/场景组合校验 → 保障时段完整性校验。

**输出格式**：

```json
{
  "complete": false,
  "intent_goal": { "user_type": "主播用户", "package_type": "直播套餐", ... },
  "profile": { "user_profile": { ... }, "application_history": { ... }, "network_kpi": { ... } },
  "missing_fields": ["scenario", "guarantee_period"],
  "schema": { ... }
}
```

- `complete=false` → 根据 `missing_fields` 自主组织自然语言追问（每轮≤3字段，最多3轮）
- `missing_fields` 含 `scenario_package_mismatch` → 向用户解释套餐与场景的对应关系
- `complete=true` → 意图完整，交由 plan_generator 生成方案

**步骤 2（可选）**：查阅参考资料

```
get_skill_reference("intent_profiler", "intent_schema.json")      # 字段规范+合法枚举+组合约束
get_skill_reference("intent_profiler", "scene_decision_tree.md")  # 场景决策树
get_skill_reference("intent_profiler", "field_rules.md")          # 字段推断规则
get_skill_reference("intent_profiler", "examples.md")             # 追问对话示例
get_skill_reference("intent_profiler", "profile_template.json")   # 完整画像模板
```

## 规则

- 模糊表述结合上下文推断，不要逐字段追问
- 能从描述推断的字段直接填充（如"卖场走播" → scenario=卖场走播场景, package_type=直播套餐）
- 套餐与场景不匹配时，先解释对应关系，再请用户确认，不要静默修正
- 关键字段（user_type / package_type / scenario / guarantee_object / guarantee_period）缺失时追问
- 非关键字段用默认值补全，不追问
- 最多追问 3 轮，超过后用合理默认值补全并告知用户

## 后续建议

意图完整（complete=true）后 → 调用 plan_generator 生成五大方案
