---
name: constraint_check
description: >
  校验填充后的方案是否可执行。检查性能约束、组网方式约束、方案间策略冲突。
  校验不通过时返回失败原因，供 Agent 决策是否回退调整方案。
  当方案填充完成后使用此 Skill。
---

# 约束校验

## 何时使用
- 方案填充完成后，验证可执行性
- Agent 判断需要检查方案冲突时

## 处理步骤
1. 调用 scripts/checker.py 依次执行三类校验
2. 返回校验结果（通过/不通过 + 原因）
3. 如果不通过，Agent 自行决定：回退调整 or 降级 or 提示用户

## 校验项
- **性能约束**：评估网关和 NCE 性能是否满足多模块指标采集需求（见 references/performance_rules.json）
- **组网方式约束**：基于设备型号/纳管/版本校验方案可行性（见 references/topology_rules.json）
- **方案冲突检测**：见 references/conflict_matrix.json

## 冲突规则示例
- 节能触发时间与重点用户保障时段重叠 → 冲突
- APPflow 策略与重点用户行为策略冲突 → 冲突
- 高敏感业务期间远程闭环触发 → 需审批
- WIFI 漫游优化与覆盖优化 → 冲突
