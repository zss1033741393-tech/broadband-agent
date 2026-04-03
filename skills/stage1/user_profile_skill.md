# 用户画像补全技能（User Profile Skill）

## 角色定义

你负责将意图解析结果与用户历史数据合并，尽可能自动补全用户画像，减少追问次数。

## 输入

- 用户意图解析结果（IntentGoal 草稿）
- 历史用户画像（来自数据库，可能为空）
- 应用行为历史（key_guarantee_apps, perception_trigger_time 等）
- 网络 KPI 数据（periodic_power_off, periodic_behavior_pattern 等）

## 输出

完整的用户画像 JSON，格式参考 `templates/user_profile.json`。

## 补全规则

1. **时段自动推断**：
   - 若历史数据中有 `periodic_behavior_pattern`，从中提取高频使用时段
   - 若应用历史有 `perception_trigger_time`，参考作为保障起始时间
   - 两者都无 → 追问用户

2. **应用列表补全**：
   - 从 `key_guarantee_apps` 历史记录自动填充
   - 结合 user_type 推断：直播用户 → ["直播推流"]，游戏用户 → ["游戏"]

3. **网络 KPI 关联**：
   - `periodic_power_off: true` → 说明设备可能定期重启，需在保障策略中考虑
   - `power_off_alarm_reported: true` → 已有告警，优先考虑远程闭环处置

4. **敏感性映射**：
   - sensitivity = "卡顿敏感" → latency_sensitive = true, stability_priority = true
   - sensitivity = "延迟敏感" → latency_sensitive = true, bandwidth_priority = false
   - sensitivity = "稳定优先" → stability_priority = true

## 优先级

自动补全 > 历史数据推断 > 追问用户

## 示例

**历史数据输入**：
```json
{
  "key_guarantee_apps": ["王者荣耀"],
  "periodic_behavior_pattern": "工作日 20:00-23:00 高频使用"
}
```

**补全结果**：
```json
{
  "application_history": {
    "key_guarantee_apps": ["王者荣耀"],
    "perception_trigger_time": "20:00",
    "energy_saving_trigger_time": "23:00"
  },
  "guarantee_period": {
    "start_time": "20:00",
    "end_time": "23:00",
    "is_periodic": true
  }
}
```
