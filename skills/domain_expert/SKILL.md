---
name: domain_expert
description: >
  【Tool Wrapper 模式】家宽 CEI 领域知识库。无执行脚本，仅提供参考资料。
  触发条件：需要查询 CEI 指标阈值（延迟/抖动/丢包告警值）、
  设备型号能力矩阵（某型号是否支持某功能）、或解释专业术语时。
  其他 Skill 执行过程中如需领域辅助判断，直接调用本 Skill 的资源文件。
---

# 领域知识库

## 资源清单

| 文件 | 内容 | 适用场景 |
|------|------|---------|
| `cei_metrics.md` | CEI 指标定义、阈值范围、计算公式（延迟/抖动/丢包/带宽利用率） | PlanAgent 填充参数时判断阈值合理性 |
| `device_capabilities.json` | 设备型号能力矩阵（型号/纳管/版本/功能支持） | ConstraintAgent 校验硬件约束；ConfigAgent 确认设备支持 |
| `glossary.md` | 术语表（CEI/NCE/ONT/QoS/RTT 等） | IntentAgent 理解用户描述中的专业词汇 |

## 如何使用

```
# 查询 CEI 指标阈值
get_skill_reference("domain_expert", "cei_metrics.md")

# 查询设备型号能力
get_skill_reference("domain_expert", "device_capabilities.json")

# 查询术语含义
get_skill_reference("domain_expert", "glossary.md")
```

## 注意
- 本 Skill 无脚本，不支持 get_skill_script 调用
- 按需加载所需资源文件，无需全部加载
