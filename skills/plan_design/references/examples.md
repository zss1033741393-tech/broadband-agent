# Plan Design Few-Shot 样例

以下三组样例覆盖场景 1（完整方案）、场景 2（稀疏方案）、场景 2 变体（仅 WIFI 启用）。

---

## 样例 1 — 场景 1：直播套餐卖场走播保抖音

**输入画像**:
```json
{
  "user_type": "主播用户",
  "package_type": "直播套餐",
  "scenario": "卖场走播",
  "guarantee_target": "STA级",
  "time_window": "18:00-22:00",
  "guarantee_app": "抖音",
  "complaint_history": true
}
```

**产出方案**:

```markdown
## WIFI 仿真方案
**启用**: true

## 差异化承载方案
**启用**: true
- 切片类型: application_slice
- 保障应用: 抖音
- 白名单: 抖音域名/IP, douyin.com, *.douyinstatic.com
- 带宽保障 (Mbps): 50

## CEI 配置方案
**启用**: true
- CEI 阈值: 70
- CEI 粒度: minute
- CEI 模型: live_streaming
- 采集时段: 18:00-22:00
- 目标 PON 口: 全部

## 故障诊断方案
**启用**: true
- 故障树: 开启
- 白名单规则: ["偶发卡顿"]
- 严重性阈值: warning

## 远程闭环处置方案
**启用**: true
- 触发时机: idle
- 操作: config_push
- 时间窗口: 18:00-22:00
- 远程覆盖弱调节: 关闭
```

**关键业务规则体现**:
- 直播套餐 → CEI 阈值 70、粒度 minute
- 卖场走播 → CEI 模型 live_streaming，远程覆盖弱调节关闭（交给 WIFI 仿真处理）
- 投诉历史 = true → 严重性阈值升级为 warning
- 直播场景 → 故障白名单加入"偶发卡顿"

---

## 样例 2 — 场景 2：区域性 PON 拥塞（Insight 回流）

**输入画像（含 insight 摘要）**:
```json
{
  "scope_indicator": "regional",
  "peak_time_window": "19:00-22:00",
  "priority_pons": ["PON-2/0/5", "PON-1/0/3"],
  "distinct_issues": ["带宽利用率过高", "丢包率超标"],
  "has_complaints": true
}
```

**产出方案**（稀疏方案，只启用差异化承载）:

```markdown
## WIFI 仿真方案
**启用**: false
_跳过原因: 区域性 PON 拥塞问题，与单用户 WIFI 无关_

## 差异化承载方案
**启用**: true
- 切片类型: appflow_traffic_shaping
- 保障应用: 视频类流量(综合)
- 白名单: 无
- 带宽保障 (Mbps): 30

## CEI 配置方案
**启用**: false
_跳过原因: 问题已通过区域性数据洞察定位，无需单用户 CEI 采集_

## 故障诊断方案
**启用**: false
_跳过原因: 已确认为拥塞问题，非设备故障_

## 远程闭环处置方案
**启用**: false
_跳过原因: 区域性拥塞需容量扩展，远程闭环无法解决_
```

---

## 样例 3 — 场景 3 变体：单点"查看 WIFI 覆盖"路径

**说明**: 场景 3 由 Orchestrator 直达 Provisioning，**通常不经过 plan_design**。如果用户的需求跨越单点边界（例如"顺便做个 CEI 配置"），PlanningAgent 才会介入，此时产出方案也是稀疏结构：

```markdown
## WIFI 仿真方案
**启用**: true

## 差异化承载方案
**启用**: false
_跳过原因: 用户仅关注 WIFI 覆盖_

## CEI 配置方案
**启用**: false
_跳过原因: 用户仅关注 WIFI 覆盖_

## 故障诊断方案
**启用**: false

## 远程闭环处置方案
**启用**: false
```

---

## 常见错误避免

1. **缺少 `**启用**: true/false` 头** → Orchestrator 无法拆分派发
2. **字段名错写**（如"阈值"代替"CEI 阈值"） → ProvisioningAgent 无法按 schema 解析
3. **禁用段不写跳过原因** → 用户体验差，也失去可追溯性
4. **业务默认值照搬所有段**（区域性问题也启用 CEI 单点采集） → 违反稀疏方案原则
