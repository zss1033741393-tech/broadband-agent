# 追问对话示例

## 示例 1 — 直播用户，信息不完整

**用户**: 我是做直播的，希望网络稳定一点

**Agent 思考**: 用户类型明确（直播用户），场景不明确（上行还是稳定性），保障时段和敏感度未知。

**Agent 追问**: 您好！为了更好地为您配置网络优化方案，请问：
1. 您一般什么时间段直播？（例如：晚上 7 点到 11 点）
2. 您对哪类问题最敏感？卡顿、延迟还是断线？

---

## 示例 2 — 游戏用户，信息较完整

**用户**: 我打游戏，晚上 9 点到 12 点，延迟高了就卡死

**Agent 思考**: 用户类型=游戏用户，保障时段=21:00-00:00，敏感点=延迟，priority_level 可推断为 high。
应用未知，但可以默认游戏类应用。

**Agent 输出**: 
```json
{
  "user_type": "游戏用户",
  "scenario": "低延迟保障",
  "guarantee_period": { "start_time": "21:00", "end_time": "00:00", "is_periodic": false },
  "guarantee_target": { "priority_level": "high", "sensitivity": "延迟", "key_applications": [] },
  "core_metrics": { "latency_sensitive": true, "bandwidth_priority": false, "stability_priority": false }
}
```

**Agent 追问**: 您主要玩什么游戏？（如王者荣耀、英雄联盟、CS2 等），这样可以更精准地配置。

---

## 示例 3 — 追问超限后用默认值补全

经过 3 轮追问后仍有缺失字段时，用合理默认值填充并说明：

**Agent**: 已基于您提供的信息和常见配置为您生成方案，以下字段使用了默认值：
- 保障时段：全天（00:00-23:59）
- 优先级：中等（medium）

如需调整，随时告诉我。
