---
name: intent_profiler
description: >
  【Inversion 模式】从用户自然语言中提取结构化意图，并用历史画像补全缺失字段。
  触发条件：用户描述保障需求、优化目标时（首次输入或补充修改）。
  完整流程：提取意图 → 画像推断补全 → 校验完整性 → 不完整则生成追问。
  追问最多3轮，超限后用默认值补全。
---

# 意图解析与画像补全

## 执行步骤

**步骤 1**：执行意图解析与画像补全：

```
get_skill_script(
    "intent_profiler",
    "analyze.py",
    execute=True,
    args=['<intent_goal_json>']   # 已知的意图字段，首次传 "{}"
)
```

脚本内部自动执行：提取意图字段 → 加载画像模板 → 用历史数据推断补全 → 校验完整性 → 生成追问。

**输出格式**：

```json
{
  "complete": false,
  "intent_goal": { "user_type": "直播用户", "scenario": "", ... },
  "profile": { "user_profile": { ... }, "application_history": { ... }, "network_kpi": { ... } },
  "missing_fields": ["scenario", "guarantee_period"],
  "followup": "您希望优化哪方面的网络体验？",
  "schema": { ... }
}
```

- `complete=false` → 用 `followup` 追问用户（每轮最多问 3 个字段）
- `complete=true` → 意图 + 画像完整，交由 plan_generator 生成方案

**步骤 2（可选）**：查阅参考资料

```
get_skill_reference("intent_profiler", "intent_schema.json")   # 字段结构定义
get_skill_reference("intent_profiler", "field_rules.md")       # 推断规则表
get_skill_reference("intent_profiler", "examples.md")          # 追问对话示例
get_skill_reference("intent_profiler", "profile_template.json") # 完整画像模板
```

## 规则
- 模糊表述结合上下文推断，不要逐字段追问
- 能从应用行为推断的字段直接补全（如"直播" → user_type=直播用户，bandwidth_priority=true）
- 关键字段（user_type / scenario / guarantee_target）缺失时追问
- 非关键字段用默认值补全，不追问
- 最多追问 3 轮，超过后用合理默认值补全并告知用户
- 从对话历史中已知字段不重复询问

## 后续建议
意图 + 画像完整后 → 调用 plan_generator 生成五大方案
