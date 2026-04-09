---
name: plan_review
description: "方案评审：对 plan_design 产出的分段方案进行约束校验，输出违规清单与修改建议"
---

# 方案评审

## Metadata
- **paradigm**: Reviewer + Tool-augmented
- **when_to_use**: PlanningAgent 生成方案 Markdown 之后、方案交给 Orchestrator 派发之前
- **inputs**: plan_design 产出的完整方案 Markdown（字符串形式）
- **outputs**: 校验结果 JSON，含 `passed / violations / recommendations / checks` 四块

## When to Use

- ✅ plan_design 已生成完整 5 段方案，需要校验后再派发
- ✅ 用户接受 `recommendations` 中的修改建议后，重新调用本 Skill 验证
- ❌ 方案尚未生成
- ❌ 单点功能执行（场景 3 路径不经过 Planning）

## 校验维度（4 大类）

| 维度 | 检查内容 | 真实场景数据源 |
|---|---|---|
| `network_topology` | 组网兼容性（目标 PON 口/切片支持度） | 拓扑库（原型 mock） |
| `performance_conflict` | 与现有策略冲突（阈值重叠/时段冲突/优先级） | 策略库（原型 mock） |
| `sla_compliance` | SLA 合规（保障时段/带宽是否超出合同） | 合同系统（原型 mock） |
| `resource_capacity` | 资源容量（目标设备负载/切片配额） | 资源管理（原型 mock） |

原型阶段**所有维度均为 mock**：`checker.py` 随机返回 3 种场景（全通过 / 通过带警告 / 未通过），未通过时**必须**同时返回 `violations` 和 `recommendations` 列表。

## How to Use

1. 接收 plan_design 产出的方案 Markdown 字符串
2. 调用脚本：
   ```
   get_skill_script(
       "plan_review",
       "checker.py",
       execute=True,
       args=["<plan_markdown_string>"]
   )
   ```
3. 读取返回的 JSON：
   - `passed`：是否通过（bool）
   - `violations`：违规项列表，每项含 `dimension / severity / message / affected_section`
   - `recommendations`：修改建议列表，每项含 `target_section / suggested_change / reason`
   - `checks`：4 大维度的检查清单（name + result: pass/warn/fail）
4. **失败处理**：PlanningAgent 把 `violations + recommendations` 交给 Orchestrator，由 Orchestrator 呈现给用户并等待决定
5. **严禁**自动修正方案重试，必须人在回路

## Scripts

- `scripts/checker.py` — 约束检查脚本（原型阶段 mock，3 种随机结果）

## Output Schema

```json
{
  "passed": true,
  "violations": [],
  "recommendations": [],
  "checks": [
    {"name": "组网兼容性检查", "dimension": "network_topology", "result": "pass"},
    {"name": "性能冲突检测", "dimension": "performance_conflict", "result": "pass"},
    {"name": "SLA 合规检查", "dimension": "sla_compliance", "result": "pass"},
    {"name": "资源容量检查", "dimension": "resource_capacity", "result": "pass"}
  ]
}
```

失败示例：
```json
{
  "passed": false,
  "violations": [
    {
      "dimension": "sla_compliance",
      "severity": "error",
      "message": "CEI 阈值 80 超出当前套餐 SLA 保障上限（70）",
      "affected_section": "CEI 配置方案"
    }
  ],
  "recommendations": [
    {
      "target_section": "CEI 配置方案",
      "suggested_change": "将 CEI 阈值从 80 降到 70 以满足 SLA 约束",
      "reason": "当前套餐 SLA 仅承诺 70 分体验保障，80 分为超配"
    }
  ],
  "checks": [...]
}
```

## 禁止事项

- ❌ 不得在失败时自动修正方案重试，必须把 `violations + recommendations` 原样返回
- ❌ 不得在本 Skill 里做业务规则判断（业务规则归属 PlanningAgent）
- ❌ 不得改写方案 Markdown 原文
