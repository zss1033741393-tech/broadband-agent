# CEI 体验指标定义

## 什么是 CEI

CEI（Customer Experience Index，用户体验指数）是衡量家宽用户网络体验的综合指标体系，
涵盖感知质量、稳定性、响应速度三个维度。

## 核心指标

### 延迟（Latency）
- **定义**: 数据包从用户设备到目标服务器的往返时间（RTT）
- **单位**: 毫秒（ms）
- **优质阈值**: < 20ms（游戏）/ < 50ms（视频）/ < 100ms（普通业务）
- **告警阈值**: > 100ms（默认）

### 抖动（Jitter）
- **定义**: 延迟的变化幅度，反映网络稳定性
- **单位**: 毫秒（ms）
- **优质阈值**: < 10ms
- **告警阈值**: > 30ms（默认）

### 丢包率（Packet Loss Rate）
- **定义**: 传输过程中丢失的数据包比例
- **单位**: 百分比（%）或小数
- **优质阈值**: < 0.1%
- **告警阈值**: > 1%（默认）

### 带宽利用率（Bandwidth Utilization Rate）
- **定义**: 实际使用带宽占签约带宽的比例
- **单位**: 百分比
- **告警阈值**: > 90%（默认），说明带宽接近饱和

## CEI 计算方法

```
CEI = w1 * Latency_Score + w2 * Stability_Score + w3 * Bandwidth_Score

其中：
- Latency_Score = max(0, 1 - latency_ms / threshold)
- Stability_Score = max(0, 1 - packet_loss_rate / threshold)
- Bandwidth_Score = max(0, 1 - bandwidth_util_rate / 0.9)
- w1 = 0.4, w2 = 0.4, w3 = 0.2（默认权重）
```

## 感知触发机制

CEI 感知采用**阈值触发**模式：
1. 持续监测核心指标
2. 当指标超过告警阈值时，记录违规次数
3. 连续 N 次违规（默认 3 次）触发告警
4. 告警上报到 NCE 平台，触发后续处置流程
