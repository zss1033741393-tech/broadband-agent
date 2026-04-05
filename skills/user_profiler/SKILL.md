---
name: user_profiler
description: >
  【Tool Wrapper 模式】查询和补全用户历史画像。
  触发条件：意图解析完成后，需要用历史 KPI、应用行为、设备信息补全画像字段。
  不负责追问用户（由 intent_parser 处理），负责从历史数据推断和补全。
---

# 用户画像补全

## 执行步骤

**步骤 1（可选）**：查看画像字段结构和补全规则：

```
get_skill_reference("user_profiler", "profile_template.json")
get_skill_reference("user_profiler", "field_rules.md")
```

**步骤 2**：执行画像查询，传入已知的用户信息（首次传 `{}`）：

```
get_skill_script(
    "user_profiler",
    "query_profile.py",
    execute=True,
    args=['<known_info_json>']
)
```

**脚本输出**：

```json
{
  "template": { "user_profile": { "user_type": "直播用户", ... } },
  "missing_fields": ["guarantee_period"],
  "field_rules": "..."
}
```

- `missing_fields` 为空 → 画像完整，继续方案填充
- `missing_fields` 不为空 → 按 field_rules 判断：能推断的补全，关键字段追问，非关键用默认值

## 规则
- 能从意图推断的字段直接补全（如"直播" → user_type=直播用户）
- 关键字段（如设备型号）缺失时追问用户
- 非关键字段用默认值补全，不追问

## 后续建议
画像完整后 → 调用 plan_generator 生成五大方案
