# 追问对话示例

## 示例1：信息完整，无需追问

**用户输入：**
> 直播套餐用户，属于卖场走播场景，需要在每天18:00-22:00高优先级保障抖音直播，此用户之前因卡顿投诉过。

**意图提取结果（complete=true）：**
```json
{
  "user_type": "主播用户",
  "package_type": "直播套餐",
  "scenario": "卖场走播场景",
  "scenario_issues": ["覆盖弱", "强干扰", "漫游问题"],
  "guarantee_object": "STA级",
  "guarantee_target": {
    "priority_level": "high",
    "sensitivity": "卡顿",
    "key_applications": ["抖音直播"],
    "sta_device": ""
  },
  "guarantee_period": {
    "start_time": "18:00",
    "end_time": "22:00",
    "is_all_day": false
  },
  "complaint_record": {
    "has_complaint": true,
    "complaint_type": "卡顿"
  },
  "core_metrics": {
    "latency_sensitive": false,
    "bandwidth_priority": true,
    "stability_priority": false
  }
}
```
**Agent 动作：** 直接调用 plan_generator，无需追问。

---

## 示例2：信息不足，需追问（普通套餐家庭用户）

**用户输入：**
> 我是主播，家里直播老是卡顿。

**第一次 analyze_intent 返回（complete=false，missing_fields=["package_type", "guarantee_period"]）**

**Agent 追问：**
> 了解到您是家庭直播用户，卡顿投诉已记录。请问您办理的是哪种套餐（普通套餐/直播套餐/专线套餐）？另外，您通常什么时间段在直播，需要重点保障网络？

**用户回复：**
> 普通套餐，晚上8点到12点直播。

**第二次 analyze_intent 返回（complete=true）：** 流程继续。

---

## 示例3：套餐与场景不匹配，需澄清

**用户输入：**
> 普通套餐，卖场走播，漫游老是断。

**第一次 analyze_intent 返回（complete=false，missing_fields=["scenario_package_mismatch"]）**

**Agent 追问：**
> 卖场走播场景通常需要直播套餐或专线套餐来支持移动漫游和 STA 级保障。请确认您的套餐类型是普通套餐还是已升级为直播套餐/专线套餐？

---

## 示例4：信息极少，多轮追问

**用户输入：**
> 我想优化网络。

**Agent 追问（第1轮）：**
> 好的，我来帮您制定优化方案。请告诉我：
> 1. 您主要是用来做什么的？（直播/游戏/其他）
> 2. 您办理的是哪种套餐？（普通套餐/直播套餐/专线套餐）

**用户回复：**
> 直播，直播套餐。

**Agent 追问（第2轮）：**
> 好的，直播套餐用户。您的直播场景主要是：在家（覆盖问题）、在卖场走播（漫游问题），还是在楼宇里（PON拥塞问题）？

**用户回复：**
> 卖场走播。

**Agent 追问（第3轮）：**
> 明白了。请问需要保障哪台设备（STA级）还是整个网络？另外，一般什么时段直播？

**超过3轮后：** 用合理默认值补全剩余字段，告知用户已使用默认配置，后续可调整。

---

## 示例5：VVIP 用户，默认高优先级

**用户输入：**
> VVIP用户，专线套餐，楼宇直播，全天保障，整网。

**意图提取结果（complete=true）：**
```json
{
  "user_type": "VVIP用户",
  "package_type": "专线套餐",
  "scenario": "楼宇直播",
  "scenario_issues": ["PON拥塞", "云服务分发问题"],
  "guarantee_object": "整网",
  "guarantee_target": { "priority_level": "high", "sensitivity": "", "key_applications": [] },
  "guarantee_period": { "start_time": "00:00", "end_time": "23:59", "is_all_day": true },
  "complaint_record": { "has_complaint": false, "complaint_type": "" }
}
```

---

## 超限默认值处理

经过 3 轮追问后仍有缺失字段，用合理默认值填充并说明：

> 已基于您提供的信息和常见配置为您生成方案，以下字段使用了默认值：
> - 保障时段：全天（00:00-23:59）
> - 优先级：中等（medium）
>
> 如需调整，随时告诉我。
