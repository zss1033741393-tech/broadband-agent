---
name: user_profiler
description: >
  查询和补全用户画像信息。从历史数据、应用行为、网络 KPI 中提取
  用户先验信息。当需要了解用户历史行为、网络状况、或补全画像字段时使用。
---

# 用户画像

## 何时使用
- 意图解析完成后，补全用户基础信息
- 需要查询用户应用行为历史
- 需要查询网络 KPI 数据

## 如何执行

**第一步**：加载指令

```
get_skill_instructions("user_profiler")
```

**第二步**：执行画像查询脚本

```
get_skill_script(
    "user_profiler",
    "query_profile.py",
    execute=True,
    args=['<known_info_json>']   # 已知的用户信息，传 "{}" 获取完整模板
)
```

**脚本输出格式（stdout JSON）**：

```json
{
  "template": { "user_profile": { "user_type": "", "scenario": "", ... } },
  "missing_fields": ["user_type", "guarantee_period"],
  "field_rules": "..."
}
```

- `missing_fields` 为空 → 画像完整，继续方案填充
- `missing_fields` 不为空 → 按 field_rules 判断哪些可推断，哪些需追问

## 规则
- 能从意图推断的字段直接补全（如用户说"直播" → user_type=直播用户）
- 关键字段缺失（如设备型号）时追问
- 非关键字段用默认值补全，不追问
