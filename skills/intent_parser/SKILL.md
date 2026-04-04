---
name: intent_parser
description: >
  解析用户自然语言输入为结构化意图目标。识别用户类型、场景、保障时段、
  保障对象、核心指标。信息不完整时生成追问。
  当用户描述保障需求、优化需求、或任何需要理解意图的场景时使用此 Skill。
---

# 意图解析

## 何时使用
- 用户首次输入保障需求描述
- 用户补充/修改需求信息
- 需要追问澄清模糊表述

## 如何执行

**第一步**：先加载指令

```
get_skill_instructions("intent_parser")
```

**第二步**：可选——读取意图目标的字段结构

```
get_skill_reference("intent_parser", "intent_schema.json")
```

**第三步**：执行意图解析脚本

```
get_skill_script(
    "intent_parser",
    "extract.py",
    execute=True,
    args=['<intent_goal_json>']   # 已提取的意图字段，首次传 "{}"
)
```

**脚本输出格式（stdout JSON）**：

```json
{
  "complete": false,
  "missing_fields": ["scenario", "guarantee_period"],
  "followup": "您希望优化哪方面的网络体验？（如：上行带宽、低延迟）",
  "schema": { ... }
}
```

- `complete=false` → 用 `followup` 中的话术向用户追问
- `complete=true` → 意图完整，继续执行下一阶段

## 规则
- 模糊表述结合上下文推断，不要逐字段追问
- 优先从用户画像 Skill 获取历史数据补全
- 追问最多 3 轮，超过后用合理默认值补全
