---
name: data_insight
description: "数据洞察分析，查询网络质量数据并进行归因分析，找出问题 PON 口和异常指标"
---

# 数据洞察分析

## Metadata
- **name**: data_insight
- **description**: 查询网络数据 + 归因分析，找出问题点
- **when_to_use**: 用户要求分析网络数据、查找问题 PON 口、分析 CEI 分数时
- **paradigm**: Tool-augmented + Workflow
- **inputs**: 用户的分析诉求（自然语言）
- **outputs**: 分析结果（数据 + 归因）

## When to Use
- ✅ 用户说"找出 CEI 分数低的 PON 口"、"分析网络质量"、"为什么 xx 指标异常"
- ✅ 主 Agent 判定为"数据洞察类"任务
- ❌ 用户要求生成配置（应使用具体功能 Skill）

## How to Use
1. 调用 `get_skill_script("data_insight", "mock_query.py", execute=True)` 查询数据
2. 分析返回的数据，识别异常点
3. 进行归因分析（原型阶段基于规则）
4. 将结果传递给 report_generation 生成报告

## Scripts
- `scripts/mock_query.py` — mock 数据查询脚本

## Examples

**输入**: "找出 CEI 分数较低的 PON 口并分析原因"
**输出**: PON 口排名 + 异常指标 + 可能原因分析
