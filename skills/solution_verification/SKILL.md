---
name: solution_verification
description: "对生成的调优方案进行约束校验，检查组网兼容性、性能冲突和 SLA 合规性"
---

# 方案校验

## Metadata
- **name**: solution_verification
- **description**: 对方案进行组网/性能/冲突校验（原型阶段为 mock）
- **when_to_use**: solution_generation 完成后，用户确认方案前进行校验
- **paradigm**: Tool-augmented + Reference
- **inputs**: 生成的方案配置
- **outputs**: 校验结果（通过/警告/不通过）

## When to Use
- ✅ 方案已生成，需要在下发前校验
- ✅ 用户主动要求"检查方案"、"校验配置"
- ❌ 方案尚未生成

## How to Use
1. 调用 `get_skill_script("solution_verification", "checker.py", execute=True)` 执行校验
2. 传入方案配置 JSON
3. 返回校验结果

## Scripts
- `scripts/checker.py` — mock 约束检查脚本

## Examples

**输入**: 方案配置 JSON
**输出**:
```json
{
  "passed": true,
  "warnings": ["时段与现有策略有重叠"],
  "errors": []
}
```
