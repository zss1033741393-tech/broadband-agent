# 用户画像字段补全规则

## 从应用行为推断

| 应用行为 | 推断字段 | 推断值 |
|---------|---------|-------|
| OBS/直播软件活跃 | user_type | 直播用户 |
| OBS/直播软件活跃 | core_metrics.bandwidth_priority | true |
| 游戏类应用活跃（Steam/WeGame 等） | user_type | 游戏用户 |
| 游戏类应用活跃 | core_metrics.latency_sensitive | true |
| 钉钉/腾讯会议/Zoom 活跃 | user_type | 办公用户 |
| 办公类应用 | core_metrics.stability_priority | true |
| 爱奇艺/优酷/B站 活跃 | user_type | 视频用户 |

## 从网络 KPI 推断

| KPI 规律 | 推断字段 | 推断值 |
|---------|---------|-------|
| 每日固定时段上行流量突增 | guarantee_period | 该时段 |
| 延迟在特定时段明显升高 | guarantee_period | 该时段 |
| 定时断电告警上报 | network_kpi.periodic_power_off | true |
| 上行带宽经常接近上限 | core_metrics.bandwidth_priority | true |
| 平均延迟 > 100ms | core_metrics.latency_sensitive | true |

## 字段默认值（无法推断时）

- guarantee_period.start_time: "00:00"
- guarantee_period.end_time: "23:59"
- guarantee_target.priority_level: "medium"
- core_metrics: 全部 false
