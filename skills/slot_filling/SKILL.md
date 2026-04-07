---
name: slot_filling
description: "综合目标场景的槽位填充引擎，通过决策树驱动追问，收集用户画像信息，输出结构化 JSON"
---

# 槽位填充引擎

## Metadata
- **name**: slot_filling
- **description**: 驱动决策树追问，收集用户画像，输出结构化 JSON
- **when_to_use**: 用户给出综合性业务目标，需要拆解用户意图并收集完整信息时
- **paradigm**: Workflow + Instructional
- **inputs**: 用户的自然语言描述
- **outputs**: 结构化用户画像 JSON（所有必填槽位已填充）

## When to Use
- ✅ 用户描述了综合性业务目标（如"直播套餐用户，保障直播"）
- ✅ 主 Agent 判定为"综合目标类"任务
- ❌ 用户直接指定了具体功能（CEI/Wifi/故障/远程闭环）
- ❌ 用户在做数据查询分析

## How to Use
1. 调用 `get_skill_script("slot_filling", "slot_engine.py", execute=True)` 初始化或更新槽位状态
2. 引擎会返回当前槽位状态和下一步需要追问的槽位
3. 根据返回的追问提示向用户提问（一次只问 1-2 个）
4. 用户回答后再次调用引擎更新状态
5. 所有必填槽位填齐后，引擎返回完整的结构化 JSON
6. 将 JSON 传递给 solution_generation 生成方案

## Scripts
- `scripts/slot_engine.py` — 槽位状态管理与追问逻辑

## Examples

**输入**: "直播套餐卖场走播用户，18:00-22:00 保障抖音直播"
**解析结果**:
```json
{
  "user_type": "主播用户",
  "package_type": "直播套餐",
  "scenario": "卖场走播",
  "guarantee_target": null,
  "time_window": "18:00-22:00",
  "complaint_history": null
}
```
**追问**: "您希望保障的范围是？（家庭网络 / STA级 / 整网）"
