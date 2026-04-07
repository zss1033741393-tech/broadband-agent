# 参数决策规则

## 用户类型 → 参数映射

### 主播用户 + 卡顿敏感
- `cei_perception.warning_threshold.latency_ms`: 100 → 50
- `cei_perception.perception_granularity.per_user_enabled`: false → true
- `cei_perception.perception_granularity.sampling_interval_sec`: 300 → 60
- `remote_closure.closure_strategy.auto_execute`: false → true
- `dynamic_optimization.realtime_optimization.enabled`: false → true
- `dynamic_optimization.realtime_optimization.qos_auto_adjust`: false → true

### 游戏用户 + 延迟敏感
- `cei_perception.warning_threshold.latency_ms`: 100 → 30
- `cei_perception.warning_threshold.jitter_ms`: 30 → 10
- `dynamic_optimization.realtime_optimization.congestion_control`: false → true
- `dynamic_optimization.realtime_optimization.enabled`: false → true

### VVIP 用户
- `remote_closure.closure_strategy.auto_execute`: false → true
- `remote_closure.closure_strategy.require_approval`: true → false
- `manual_fallback.trigger_conditions.high_priority_user`: false → true
- `manual_fallback.dispatch_policy.priority_level`: "medium" → "high"
- `manual_fallback.dispatch_policy.expected_response_minutes`: 30 → 15

## 套餐类型 → 参数映射

### 专线套餐
- `dynamic_optimization.realtime_optimization.enabled`: false → true
- `dynamic_optimization.realtime_optimization.qos_auto_adjust`: false → true
- QoS 策略全开，上行带宽预留更高（≥90%）

### 直播套餐
- per_user 感知按需开启（场景决定）
- 实时优化开启

### 普通套餐
- 保守策略，需审批
- `remote_closure.closure_strategy.require_approval`: 保持 true

## 场景 → 参数映射

### 卖场走播场景
- `cei_perception.perception_granularity.per_user_enabled`: false → true
- `cei_perception.perception_granularity.sampling_interval_sec`: 300 → 30（加密采集）
- `dynamic_optimization.wifi_optimization.roaming_optimization`: false → true（WiFi 漫游优化必须开启）

### 楼宇直播
- `cei_perception.warning_threshold.bandwidth_util_rate`: 0.9 → 0.7（PON 拥塞早预警）
- 关注 PON 上行拥塞和云端推流链路

### 家庭直播用户
- 上行带宽优先，覆盖优化
- `dynamic_optimization.realtime_optimization.qos_auto_adjust`: false → true

## 保障对象 → 参数映射

### STA 级
- `cei_perception.perception_granularity.per_user_enabled`: **必须** false → true

### 整网
- 全局策略，所有设备均受保障

### 家庭网络
- 家庭级感知，不需要 per_user

## 投诉记录 → 参数映射

### has_complaint=true
- `cei_perception.perception_granularity.sampling_interval_sec`: 降至 30s（加密采集）
- `manual_fallback.trigger_conditions.high_priority_user`: false → true
- `manual_fallback.dispatch_policy.priority_level`: "medium" → "high"
- `manual_fallback.dispatch_policy.expected_response_minutes`: 30 → 15

## 保障时段 → 参数映射

- 非全天保障 → `cei_perception.trigger_window` 填入用户指定时段，`all_day` 设为 false
- 全天保障 → 保持默认 00:00-23:59，`all_day` 保持 true

## 敏感点 → 参数映射

- 卡顿敏感 → `cei_perception.warning_threshold.bandwidth_util_rate`: 0.9 → 0.75
- 延迟敏感 → `cei_perception.warning_threshold.latency_ms` 降至 30
- 断线敏感 → `remote_closure.closure_strategy.fallback_to_manual`: true

## 高优先级用户

- priority_level = "high" → `manual_fallback.trigger_conditions.high_priority_user`: true
- priority_level = "high" → `manual_fallback.dispatch_policy.expected_response_minutes`: 30 → 15
- priority_level = "high" → `remote_closure.closure_strategy.require_approval`: true → false

## 约束校验回退 → 调整策略

- 性能约束不满足（采集粒度过细）→ `sampling_interval_sec` 增大（30→60→120）
- 节能时段与保障时段冲突 → 调整 `dynamic_optimization.energy_saving.trigger_time` 避开保障时段
- WIFI 漫游优化与覆盖优化冲突 → 关闭 `coverage_optimization`，保留 `roaming_optimization`
- APPflow 与重点用户行为策略冲突 → 关闭 APPflow（降优先级策略）
