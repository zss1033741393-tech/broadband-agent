# 家宽领域知识技能（Domain Knowledge Skill）

## 角色定义

你掌握家庭宽带体验优化的领域知识，在方案填充时提供参数取值的合理范围和业务含义指导。

## 核心指标说明

### CEI（Customer Experience Index）— 用户体验指数

| 指标 | 说明 | 正常范围 | 告警阈值建议 |
|------|------|---------|------------|
| latency_ms | 网络延迟（毫秒） | < 50ms 优秀 | 50-100ms 正常，>100ms 告警 |
| packet_loss_rate | 丢包率 | < 0.1% 优秀 | > 1% 告警 |
| jitter_ms | 延迟抖动（毫秒） | < 10ms 优秀 | > 30ms 影响实时业务 |
| throughput_min_mbps | 最低带宽保障 | 取决于套餐 | 直播上行 ≥ 10Mbps，游戏 ≥ 20Mbps |

### 感知粒度参数

| 参数 | 说明 | 建议取值 |
|------|------|---------|
| sampling_interval_sec | 采样间隔（秒） | 普通用户: 300s，高优用户: 60s |
| aggregation_window_min | 聚合窗口（分钟） | 15min（短期），60min（长期趋势） |
| per_user_enabled | 是否精细化到单用户 | 仅高优先级场景开启 |

## 用户类型特征

### 直播用户
- 核心需求：上行带宽充足、延迟稳定
- 关键时段：通常为晚间 19:00-23:00
- 核心指标：upload_throughput > 10Mbps，latency < 50ms
- APPflow 策略：直播推流流量优先保障

### 游戏用户
- 核心需求：下行延迟低、抖动小
- 关键时段：晚间 19:00-23:00，周末全天
- 核心指标：latency < 30ms，jitter < 10ms
- APPflow 策略：游戏流量最高优先级

### 办公用户
- 核心需求：视频会议稳定、断线重连快
- 关键时段：工作日 9:00-18:00
- 核心指标：latency < 100ms，stability 高

## 闭环操作说明

| 操作 | 适用场景 | 风险 |
|------|---------|------|
| port_reset | 端口故障、光信号异常 | 短暂断网（< 30s） |
| bandwidth_adjustment | 带宽不足 | 可能影响其他用户 |
| channel_switch | WiFi 信道拥塞 | 短暂重连 |
| firmware_upgrade | 设备 Bug | 重启，高风险 |

**重要**：高优先级用户（直播/游戏关键时段）内不建议执行 firmware_upgrade，应在保障时段外执行。

## 参数合理范围约束

- latency_ms 告警阈值：[20, 500] ms
- packet_loss_rate 告警阈值：[0.001, 0.1]
- sampling_interval_sec：[30, 3600] 秒
- max_retry：[1, 10] 次
- sla_response_hour：[1, 72] 小时
