---
name: plan_filling
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

## 处理步骤
1. 读取 IntentGoal
2. 遍历 references/ 中的 5 个方案模板 JSON
3. 对照 references/filling_rules.md 判断每个模板中哪些参数需要修改
4. 调用 scripts/filler.py 执行填充
5. 输出填充后的方案 JSON + 修改说明

## 规则
- 不需要修改的参数保持模板默认值
- 五个模板相互独立，可并行处理（asyncio.gather）
- 填充后在修改说明中列出每个被改的字段和原因
- 如果是约束校验回退，只调整冲突相关的参数

## 参数决策规则速查
见 references/filling_rules.md
