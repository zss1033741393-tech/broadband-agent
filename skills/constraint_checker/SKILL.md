---
name: constraint_checker
description: >
  【Reviewer 模式】校验方案是否满足性能约束、组网约束和策略冲突规则。
  触发条件：方案填充完成后（必须执行，不可跳过）；或方案调整后重新校验。
  校验不通过时返回 suggestions 供 PlanAgent 修正。
---

# 约束校验（强制步骤）

## 执行步骤

**推荐方式（直接 Python 工具，无 subprocess 开销）**：

```
plans_file = get_pipeline_file("plans")   # → "outputs/<sid>/plans.json"
check_constraints(plans_file)
# intent_goal 可省略，工具自动从 outputs/<sid>/intent.json 读取
```

**备用方式（subprocess，CLI 调试时使用）**：

```
get_skill_script(
    "constraint_checker",
    "validate.py",
    execute=True,
    args=["--plans-file", "outputs/<sid>/plans.json",
          "--intent-file", "outputs/<sid>/intent.json"]
)
```

> `validate.py` 自动加载以下规则文件，无需提前读取：
> - `references/performance_rules.json` — 采集间隔、CPU 负载约束
> - `references/conflict_matrix.json` — 节能时段 vs 保障时段、WiFi 策略冲突
> - `references/topology_rules.json` — 设备型号/纳管/版本组网约束

**输出格式**：

```json
{
  "passed": false,
  "conflicts": ["CONF_001: 节能触发时间 20:00 与保障时段 19:00-23:00 重叠"],
  "warnings": ["PERF_003: 自动诊断开启时，采集间隔建议不低于 60 秒"],
  "failed_checks": ["CONF_001"],
  "suggestions": ["将节能触发时间调整到保障时段之外"]
}
```

## 处理规则
- `passed=true` → 进入配置转译
- `conflicts` 非空（severity=error）→ 将 suggestions 返回给主控，由 PlanAgent 重新生成
- `warnings` 非空（severity=warning）→ 告知用户风险，等待确认后继续
- 连续 3 次失败 → 声明需人工介入

## 后续建议
校验通过后 → 调用 config_translator 生成设备配置
