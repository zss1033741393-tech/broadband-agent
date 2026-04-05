---
name: intent_parser
description: >
  【Inversion 模式】从用户自然语言中提取结构化 IntentGoal。
  触发条件：用户描述保障需求、优化目标、或任何涉及"想保障什么/优化什么"的表述。
  负责字段提取和追问，不负责历史画像补全（由 user_profiler 处理）。
---

# 意图解析

## 执行步骤

**步骤 1（可选）**：如需了解 IntentGoal 字段结构，加载 schema：

```
get_skill_reference("intent_parser", "intent_schema.json")
```

**步骤 2**：执行意图解析，传入当前已提取的意图字段（首次传 `{}`）：

```
get_skill_script(
    "intent_parser",
    "extract.py",
    execute=True,
    args=['<intent_goal_json>']
)
```

**脚本输出**：

```json
{
  "complete": false,
  "missing_fields": ["scenario", "guarantee_period"],
  "followup": "您希望优化哪方面的网络体验？",
  "schema": { ... }
}
```

- `complete=false` → 用 `followup` 追问用户，每轮最多问 3 个字段
- `complete=true` → 意图完整，交由 user_profiler 补全画像

## 规则
- 模糊表述结合上下文推断，不要逐字段追问
- 最多追问 3 轮，超过后用合理默认值补全
- 从对话历史或 user_profiler 已知字段中推断，避免重复询问

## 后续建议
意图完整后 → 调用 user_profiler 补全用户画像
