# 参数决策规则

## 用户类型 → 参数映射

### 直播用户 + 卡顿敏感
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

### 办公用户 + 稳定性优先
- `cei_perception.warning_threshold.packet_loss_rate`: 0.01 → 0.001
- `dynamic_optimization.habit_pre_optimization.enabled`: false → true
- `manual_fallback.trigger_conditions.high_priority_user`: false → true
- `manual_fallback.dispatch_policy.priority_level`: "medium" → "high"

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
- 性能约束不满足（采集粒度过细）→ `sampling_interval_sec` 增大（60→120）
- 节能时段与保障时段冲突 → 调整 `dynamic_optimization.energy_saving.trigger_time` 避开保障时段
- WIFI 漫游优化与覆盖优化冲突 → 关闭 `coverage_optimization`，保留 `roaming_optimization`
- APPflow 与重点用户行为策略冲突 → 关闭 APPflow（降优先级策略）
