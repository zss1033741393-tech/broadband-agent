---
name: wifi_simulation
description: "WIFI 仿真：内部驱动户型图识别→热力图→RSSI 采集→选点对比 4 步，产出可视化图表与选点建议"
---

# WIFI 仿真

## Metadata
- **paradigm**: Pipeline (内部 4 步串行,对 Agent 表现为一次调用)
- **when_to_use**: ProvisioningWifiAgent 需要执行 WIFI 仿真、评估覆盖、查看信号强度或给出选点建议
- **inputs**: 仿真参数（户型描述、楼层等，可选）
- **outputs**: 4 步产物组合 JSON + 每步的 ECharts 可视化

## Parameter Schema

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `floor_plan_hint` | string | 否 | `三室一厅` | 户型线索（自然语言描述或默认） |
| `area_sqm` | int | 否 | `100` | 房屋面积（平方米） |
| `wall_material` | string | 否 | `brick` | 墙体材质：`brick` / `concrete` / `wood` / `glass` |

## 内部 4 步流水线（由 `simulate.py` 脚本驱动）

| 步骤 | 功能 | 产出 |
|---|---|---|
| 1. 户型图识别 | Mock 识别户型结构 → 房间布局 | `rooms` 列表 + 户型示意图 ECharts (graph) |
| 2. 热力图生成 | 基于布局模拟信号覆盖 | `heatmap` 2D 数据 + ECharts heatmap |
| 3. RSSI 采集 | 采样各房间 RSSI 值 | `rssi_samples` + 柱状图 ECharts |
| 4. 选点对比 | 对比现有 AP 与推荐 AP 位置 | `ap_recommendation` + before/after 热力对比 |

## When to Use

- ✅ Provisioning 接收方案段落含"WIFI 仿真方案: **启用**: true"
- ✅ 场景 3 单点指令：用户要求"查看 WIFI 覆盖"或"做个仿真" — 任务头 `[任务类型: WIFI 仿真执行]`
- ❌ 用户只是问 WIFI 概念
- ❌ 用户要求 Appflow 或切片（应走 `differentiated_delivery`）

## How to Use

1. ProvisioningAgent 按 schema 组装参数 JSON（或传 `{}` 使用默认户型）
2. 调用脚本：
   ```
   get_skill_script(
       "wifi_simulation",
       "simulate.py",
       execute=True,
       args=["<params_json_string>"]
   )
   ```
3. 脚本按序执行 4 步，每步产出图表数据 + 状态摘要
4. 最终返回包含 4 步产物的完整 JSON，**Agent 透传给用户**（不得改写 ECharts 配置）

## Output Schema

```json
{
  "skill": "wifi_simulation",
  "params": {...},
  "steps": [
    {
      "step": 1,
      "name": "户型图识别",
      "status": "success",
      "result": {"rooms": [...]},
      "echarts_option": { ... graph ... }
    },
    {
      "step": 2,
      "name": "热力图生成",
      "status": "success",
      "result": {"heatmap_grid": [...]},
      "echarts_option": { ... heatmap ... }
    },
    {
      "step": 3,
      "name": "RSSI 采集",
      "status": "success",
      "result": {"rssi_samples": [...]},
      "echarts_option": { ... bar ... }
    },
    {
      "step": 4,
      "name": "选点对比",
      "status": "success",
      "result": {"current_ap": [...], "recommended_ap": [...], "improvement_dbm": 7},
      "echarts_option": { ... heatmap comparison ... }
    }
  ],
  "summary": "建议将主 AP 从客厅迁移至走廊，覆盖弱点改善 7 dBm"
}
```

## Scripts

- `scripts/simulate.py` — 内部 4 步流水线执行器（mock 实现）

## References

- `references/default_wifi.yaml` — 默认户型与 AP 参考配置

## 禁止事项

- ❌ 不得拆成多次 Skill 调用（4 步在脚本内部完成）
- ❌ 不得改写或简化 ECharts 配置
