---
name: domain_expert
description: >
  家宽领域专业知识。包含 CEI 指标定义、设备型号能力矩阵、术语表。
  当 Agent 需要理解专业概念、查询设备能力、或解释术语时使用此 Skill。
  此 Skill 仅提供参考资料，无执行脚本。领域知识已灌入 Knowledge RAG，
  优先使用 knowledge 检索，其次使用 get_skill_reference 读取文件。
---

# 领域知识

## 何时使用
- 其他 Skill 执行中需要领域知识辅助判断
- 用户询问专业术语含义
- 需要查询设备型号支持哪些功能
- 需要了解 CEI 指标计算方法

## 如何查询

**优先**：使用 knowledge 语义检索（已向量化）

```
search_knowledge("CEI 延迟指标计算方法")
search_knowledge("华为 AX3 Pro 设备能力")
```

**备选**：直接读取参考文件

```
get_skill_reference("domain_expert", "cei_metrics.md")
get_skill_reference("domain_expert", "glossary.md")
get_skill_reference("domain_expert", "device_capabilities.json")
```

## 资源清单
- `references/cei_metrics.md` — CEI 体验指标定义、计算方法、阈值范围
- `references/device_capabilities.json` — 设备型号能力矩阵（型号/纳管/版本/功能支持）
- `references/glossary.md` — 术语表（CEI / NMS / NCE / APPflow 等）

## 注意
此 Skill 无脚本，不支持 get_skill_script 调用。
