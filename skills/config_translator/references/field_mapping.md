# 语义字段 → 设备字段映射表

## 感知配置（perception）

| 语义字段路径 | 设备字段名 | 类型 | 说明 |
|------------|----------|------|------|
| `cei_perception.warning_threshold.latency_ms` | `cei_warn_latency_threshold` | integer | 延迟告警阈值（ms） |
| `cei_perception.warning_threshold.packet_loss_rate` | `cei_warn_loss_threshold` | number | 丢包率告警阈值 |
| `cei_perception.warning_threshold.jitter_ms` | `cei_warn_jitter_threshold` | integer | 抖动告警阈值（ms） |
| `cei_perception.perception_granularity.sampling_interval_sec` | `cei_collect_interval` | integer | 采集间隔（秒） |
| `cei_perception.perception_granularity.per_user_enabled` | `cei_per_user_mode` | boolean | 是否开启用户级感知 |
| `cei_perception.trigger_window.start_time` | `cei_trigger_start` | string | 感知触发开始时间 |
| `cei_perception.trigger_window.end_time` | `cei_trigger_end` | string | 感知触发结束时间 |

## 远程闭环配置（closure）

| 语义字段路径 | 设备字段名 | 类型 | 说明 |
|------------|----------|------|------|
| `remote_closure.closure_strategy.auto_execute` | `closure_auto_exec` | boolean | 是否自动执行闭环 |
| `remote_closure.closure_strategy.require_approval` | `closure_need_approval` | boolean | 是否需要审批 |
| `remote_closure.sensitivity_guard.block_during_guarantee_period` | `closure_block_in_guarantee` | boolean | 保障期屏蔽闭环 |

## 智能优化配置（optimization）

| 语义字段路径 | 设备字段名 | 类型 | 说明 |
|------------|----------|------|------|
| `dynamic_optimization.realtime_optimization.enabled` | `opt_realtime_enable` | boolean | 是否开启实时优化 |
| `dynamic_optimization.realtime_optimization.qos_auto_adjust` | `opt_qos_auto` | boolean | QoS 自动调整 |
| `dynamic_optimization.realtime_optimization.congestion_control` | `opt_congestion_ctrl` | boolean | 拥塞控制 |
| `dynamic_optimization.energy_saving.enabled` | `opt_energy_save_enable` | boolean | 是否开启节能 |
| `dynamic_optimization.energy_saving.trigger_time` | `opt_energy_save_start` | string | 节能开始时间 |
| `dynamic_optimization.energy_saving.resume_time` | `opt_energy_save_end` | string | 节能结束时间 |
