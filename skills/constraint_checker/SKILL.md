---
name: constraint_checker
description: >
  校验填充后的方案是否可执行。检查性能约束、组网方式约束、方案间策略冲突。
  校验不通过时返回失败原因，供 Agent 决策是否回退调整方案。
  当方案填充完成后使用此 Skill。这是强制步骤，不可跳过。
---

# 约束校验（强制步骤）

## 何时使用
- 方案填充完成后，验证可执行性（**必须执行**）
- Agent 修正方案后，重新校验

## 如何执行

**第一步**：加载指令

```
get_skill_instructions("constraint_checker")
```

**第二步**：执行约束校验脚本

```
get_skill_script(
    "constraint_checker",
    "validate.py",
    execute=True,
    args=['<plans_json>', '<intent_goal_json>']
)
```

- `plans_json`：plan_generator 返回的 `plans` 数组转成 dict（key 为 template 文件名）
- `intent_goal_json`：完整的 IntentGoal JSON（含 guarantee_period 等字段）

**脚本输出格式（stdout JSON）**：

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
- conflicts 非空（severity=error）→ 根据 suggestions 自动调整方案，重新校验
- warnings 非空（severity=warning）→ 向用户说明风险，等待确认
- 连续 3 次失败 → 声明需人工介入

## 校验类型
- **性能约束**：采集间隔、CPU 负载（references/performance_rules.json）
- **组网约束**：设备型号/纳管/版本（references/topology_rules.json）
- **冲突检测**：节能时段 vs 保障时段、WiFi 策略冲突（references/conflict_matrix.json）
