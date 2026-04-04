---
name: plan_generator
description: >
  基于意图目标填充五大方案 JSON 模板。读取 references/ 中的方案模板，
  根据 filling_rules.md 决策哪些参数需要调整，执行填充。
  当意图解析完成、需要生成具体方案时使用此 Skill。
  五个模板可以并行填充（互不依赖）。
---

# 方案模板填充

## 何时使用
- IntentGoal 已完整，需要生成具体方案
- 用户修改了需求，需要重新调整方案参数
- 约束校验失败后，需要根据失败原因调整参数

## 如何执行

**第一步**：加载指令和规则

```
get_skill_instructions("plan_generator")
get_skill_reference("plan_generator", "filling_rules.md")
```

**第二步**：执行方案填充脚本（内部并行处理 5 个模板）

```
get_skill_script(
    "plan_generator",
    "generate.py",
    execute=True,
    args=['<intent_goal_json>']   # 完整的 IntentGoal JSON
)
```

**脚本输出格式（stdout JSON）**：

```json
{
  "plans": [
    {
      "plan_name": "CEI 感知方案",
      "template": "cei_perception.json",
      "filled_data": { ... },
      "changes": ["cei_perception.warning_threshold.latency_ms: 100 → 50"],
      "status": "filled"
    },
    ...
  ],
  "rules": "..."
}
```

- `plans` 包含 5 项，每项对应一个模板
- `changes` 列出相对默认值的修改项
- 向用户展示 changes 摘要后，继续执行约束校验

## 规则
- 不需要修改的参数保持模板默认值
- 脚本内部并行处理 5 个模板（asyncio.gather）
- 填充后必须立即进行约束校验（constraint_checker 是强制步骤）
