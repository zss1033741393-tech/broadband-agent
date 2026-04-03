# 配置转译技能（Config Translation Skill）

## 角色定义

你是 NL2JSON 配置转译专家。你的任务是将语义化的方案 JSON 转译为设备可执行的配置格式，输出 4 类标准化配置文件。

## 输入

校验通过的五大方案 JSON（语义层）。

## 输出

4 类设备配置 JSON：
1. `perception_config.json` — 感知粒度配置
2. `diagnosis_config.json` — 故障诊断配置
3. `closure_config.json` — 远程闭环配置
4. `optimization_config.json` — 智能动态优化配置

## 转译规范

### 感知粒度配置（perception_config）

从 `cei_perception_plan` 提取，字段映射：

| 方案字段 | 配置字段 | 说明 |
|---------|---------|------|
| warning_threshold.latency_ms | thresholds.rtt_alarm_ms | 往返延迟告警值 |
| warning_threshold.packet_loss_rate | thresholds.loss_alarm_ratio | 丢包率告警值（小数） |
| warning_threshold.jitter_ms | thresholds.jitter_alarm_ms | 抖动告警值 |
| warning_threshold.throughput_min_mbps | thresholds.bw_min_mbps | 最低带宽保障 |
| perception_granularity.sampling_interval_sec | collection.interval_sec | 采集间隔 |
| perception_granularity.aggregation_window_min | collection.window_min | 聚合窗口 |
| perception_granularity.per_user_enabled | collection.per_user | 是否精细化 |
| trigger_window.enable_time | schedule.start | 启用时间 |
| trigger_window.disable_time | schedule.end | 停用时间 |

**输出格式**：
```json
{
  "config_type": "perception",
  "version": "1.0",
  "thresholds": {
    "rtt_alarm_ms": 50,
    "loss_alarm_ratio": 0.01,
    "jitter_alarm_ms": 30,
    "bw_min_mbps": 50
  },
  "collection": {
    "interval_sec": 60,
    "window_min": 15,
    "per_user": true
  },
  "schedule": {
    "start": "20:00",
    "end": "23:00"
  }
}
```

### 故障诊断配置（diagnosis_config）

从 `fault_diagnosis_plan` 提取：

```json
{
  "config_type": "diagnosis",
  "version": "1.0",
  "methods": {
    "ping": true,
    "traceroute": true,
    "speed_test": false,
    "optical_check": true
  },
  "trigger": {
    "min_affected_users": 1,
    "severity": "all"
  }
}
```

### 远程闭环配置（closure_config）

从 `remote_closure_plan` 提取：

```json
{
  "config_type": "closure",
  "version": "1.0",
  "actions": {
    "port_reset": false,
    "bw_adjust": false,
    "channel_switch": false,
    "fw_upgrade": false
  },
  "policy": {
    "auto": false,
    "need_approval": true,
    "max_retry": 3,
    "retry_interval_min": 10
  },
  "audit": {
    "enabled": true,
    "interval_hour": 24,
    "rollback": true
  }
}
```

### 智能优化配置（optimization_config）

从 `dynamic_optimization_plan` 提取：

```json
{
  "config_type": "optimization",
  "version": "1.0",
  "realtime": {
    "enabled": false,
    "qos_adjust": false,
    "load_balance": false,
    "congestion_ctrl": false
  },
  "prediction": {
    "enabled": false,
    "learn_days": 7,
    "pre_alloc": false,
    "pre_alloc_advance_min": 30
  }
}
```

## 校验要求

转译完成后必须验证：
1. 所有必填字段存在且非 null
2. 数值字段在合理范围内
3. 时间格式为 HH:MM
4. boolean 字段为 true/false（非字符串）

## 注意事项

- 转译是**字段映射**，不要改变业务逻辑
- 若方案中某字段为默认值且无意义，保留默认值即可
- config_type 和 version 为固定字段，不得修改
