---
name: report_generation
description: "聚合分析结果或方案配置，渲染为结构化 Markdown 报告"
---

# 报告生成

## Metadata
- **name**: report_generation
- **description**: 聚合结果渲染 Markdown 报告
- **when_to_use**: 方案生成完成后 或 数据洞察分析完成后，需要生成汇总报告
- **paradigm**: Template + Instructional
- **inputs**: 方案配置 或 分析结果
- **outputs**: Markdown 格式报告

## When to Use
- ✅ 综合目标流程的最后一步，汇总所有配置
- ✅ 数据洞察完成后生成分析报告
- ❌ 流程中间步骤，不需要报告

## How to Use
1. 收集前序步骤的输出（方案配置 或 分析数据）
2. 使用 `templates/report.md.j2` 渲染报告
3. 展示报告给用户

## Templates / References
- `templates/report.md.j2` — Markdown 报告模板

## Examples

**输入**: 方案配置 + 校验结果
**输出**: 结构化 Markdown 报告
