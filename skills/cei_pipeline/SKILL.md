---
name: cei_pipeline
description: "CEI 体验感知流水线：根据传入参数渲染 Spark 配置，完成 CEI 采集→评分→阈值告警配置下发"
---

# CEI 体验感知流水线

## Metadata
- **paradigm**: Generator (参数 schema 驱动，纯模板填空)
- **when_to_use**: ProvisioningCeiChainAgent 需要根据方案段落或单点指令生成 CEI Spark 配置时
- **inputs**: JSON 参数（schema 见下）
- **outputs**: 渲染后的 CEI Spark YAML 配置 + mock 下发结果

## Parameter Schema（Provisioning 按此从方案段落提参）

| 字段 | 类型 | 必填 | 默认值 | 允许值 | 说明 |
|---|---|---|---|---|---|
| `threshold` | int | 是 | 70 | 0-100 | CEI 告警阈值分数（低于此值触发告警） |
| `granularity` | string | 是 | `minute` | `minute` / `hour` | 采集粒度 |
| `model` | string | 是 | `general` | `live_streaming` / `gaming` / `general` / `vvip` | 评分模型 |
| `time_window` | string | 是 | `全天` | — | 保障时段，如 `18:00-22:00` 或 `全天` |
| `target_pon` | string | 否 | `全部` | PON-x/x/x 或 `全部` | 目标 PON 口，空/"全部"表示全部 PON 口 |

**本 Skill 不做业务规则判断**（不根据套餐推阈值、不根据场景选模型），业务规则由 PlanningAgent 在生成方案时已经决定。本 Skill 只做"参数 → 配置 YAML"的纯格式转换。

## When to Use

- ✅ Provisioning 接收的方案段落中有"CEI 配置方案: **启用**: true"
- ✅ 场景 3 单点指令（如"CEI 阈值调整为 75"）— 任务头 `[任务类型: 单点 CEI 配置]`
- ✅ 完整保障链的第一步（任务头 `[任务类型: 完整保障链]`）
- ❌ 用户只是问 CEI 概念（直接回答）
- ❌ 用户要求数据洞察（应走 data_insight）

## How to Use

1. ProvisioningAgent 从方案段落中按 schema 提取参数，组装 JSON 字符串
2. 调用脚本：
   ```
   get_skill_script(
       "cei_pipeline",
       "render.py",
       execute=True,
       args=["<params_json_string>"]
   )
   ```
3. 脚本读取 `references/cei_spark.yaml.j2` 模板，用参数填空后输出 `{yaml_config, dispatch_result}` JSON
4. 将完整 JSON 透传给用户展示（不得改写）

## Scripts

- `scripts/render.py` — 读取模板 + 参数填空 + 调用 mock 下发客户端

## References

- `references/cei_spark.yaml.j2` — Spark 配置模板（纯参数占位符，无业务条件分支）

## Examples

**输入**:
```json
{
  "threshold": 70,
  "granularity": "minute",
  "model": "live_streaming",
  "time_window": "18:00-22:00",
  "target_pon": "全部"
}
```

**输出**:
```json
{
  "params": {...},
  "yaml_config": "cei_spark:\n  target_pon: ...",
  "dispatch_result": {"status": "success", "config_id": "CEI-..."}
}
```

## 禁止事项

- ❌ 不做业务规则推断（不根据套餐/场景补默认值，业务规则归属 PlanningAgent）
- ❌ 模板不得使用 `{% if %}` 进行业务逻辑分支（仅允许参数填空）
