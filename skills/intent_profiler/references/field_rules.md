# 用户画像字段推断规则

## 从用户描述推断

| 用户描述关键词 | 推断字段 | 推断值 |
|--------------|---------|-------|
| 直播 / 主播 / 开播 | user_type | 主播用户 |
| 直播 / 主播 | core_metrics.bandwidth_priority | true |
| 游戏 / 打游戏 / 竞技 | user_type | 游戏用户 |
| 游戏 / 打游戏 | core_metrics.latency_sensitive | true |
| VVIP / 大客户 / 高价值 | user_type | VVIP用户 |
| 家里直播 / 家庭网络 / 覆盖差/弱 | scenario | 家庭直播用户 |
| 家里直播 / 家庭网络 | package_type | 普通套餐 |
| 卖场 / 走播 / 商场 / 展厅 / 漫游 | scenario | 卖场走播场景 |
| 卖场 / 走播 | package_type | 直播套餐（若未提及专线） |
| 楼宇 / 商业体 / PON / 推流卡 | scenario | 楼宇直播 |
| 楼宇 / 商业体 | package_type | 直播套餐（若未提及专线） |
| 专线 / 高保障 / 高优先级 | package_type | 专线套餐 |
| 卡顿 / 投诉过 / 反馈过 | complaint_record.has_complaint | true |
| 卡顿 / 投诉过 | guarantee_target.priority_level | high |
| 卡顿 | guarantee_target.sensitivity | 卡顿 |
| 延迟高 / 延迟大 / 卡 | guarantee_target.sensitivity | 延迟 |
| 断线 / 掉线 / 断网 | guarantee_target.sensitivity | 断线 |
| 高优先级 / 优先保障 / 重点 | guarantee_target.priority_level | high |
| 指定设备 / 某台设备 / 这台电脑 | guarantee_object | STA级 |
| 全部设备 / 整网 / 所有 | guarantee_object | 整网 |
| 家庭网络 / 家里所有 | guarantee_object | 家庭网络 |
| 抖音直播 / 快手直播 / 虎牙直播 | guarantee_target.key_applications | 对应平台名称 |
| 王者荣耀 / 英雄联盟 / 和平精英 | guarantee_target.key_applications | 对应游戏名称 |

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
- guarantee_period.is_all_day: true（若未提及时段则默认全天）
- guarantee_target.priority_level: "medium"（无投诉则默认中等）
- complaint_record.has_complaint: false
- core_metrics: 全部 false

## 优先级推断规则

- VVIP用户 → priority_level 默认 high
- has_complaint=true → priority_level 至少 high
- 专线套餐 → priority_level 默认 high
