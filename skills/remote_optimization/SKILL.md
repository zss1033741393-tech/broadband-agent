---
name: remote_optimization
description: "远程优化：根据传入参数渲染远程闭环动作配置 JSON（网关重启/配置下发/覆盖调节等）"
---

# 远程优化

## Metadata
- **paradigm**: Generator (参数 schema 驱动)
- **when_to_use**: ProvisioningCeiChainAgent 需要配置远程优化动作，或用户单点远程操作指令
- **inputs**: JSON 参数（schema 见下）
- **outputs**: 远程优化配置 JSON + mock 执行结果

## Parameter Schema

| 字段 | 类型 | 必填 | 默认值 | 允许值 | 说明 |
|---|---|---|---|---|---|
| `trigger_mode` | string | 是 | `idle` | `immediate` / `idle` / `scheduled` | 触发时机 |
| `action` | string | 是 | `config_push` | `gateway_restart` / `config_push` / `coverage_tune` / `speed_test` | 远程动作类型 |
| `time_window` | string | 否 | `全天` | — | 允许执行的时间窗口 |
| `coverage_weak_enabled` | bool | 否 | `false` | — | 是否启用覆盖弱自动调节（卖场走播等场景建议关闭） |

## When to Use

- ✅ Provisioning 接收方案段落含"远程闭环处置方案: **启用**: true"
- ✅ 场景 3 单点指令：用户要求"立即重启网关"或"闲时远程优化" — 任务头 `[任务类型: 单点远程操作]`
- ✅ 完整保障链的第三步（故障可远程修复时触发）
- ❌ 需要现场工程师处置的问题（应上报人工）

## How to Use

1. ProvisioningAgent 按 schema 组装参数 JSON
2. 调用脚本：
   ```
   get_skill_script(
       "remote_optimization",
       "render.py",
       execute=True,
       args=["<params_json_string>"]
   )
   ```
3. 脚本渲染配置 + mock 执行，返回 `{params, config_json, dispatch_result}` JSON
4. 透传给用户展示

## Scripts

- `scripts/render.py` — 模板渲染 + mock 执行

## References

- `references/remote_loop.json.j2` — 远程闭环配置 Jinja2 模板

## Examples

**输入**:
```json
{
  "trigger_mode": "idle",
  "action": "config_push",
  "time_window": "18:00-22:00",
  "coverage_weak_enabled": false
}
```

**输出**:
```json
{
  "skill": "remote_optimization",
  "params": {...},
  "config_json": "{ ... 远程动作配置 ... }",
  "dispatch_result": {"status": "success", "loop_id": "LOOP-..."}
}
```

## 禁止事项

- ❌ 不做业务规则推断（如"直播场景默认关闭覆盖弱"由 PlanningAgent 决定）
- ❌ 不得跳过 schema 校验直接下发
