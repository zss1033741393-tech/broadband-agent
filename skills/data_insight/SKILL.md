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
5. 若用户随后要求生成优化方案，将完整输出（含 `config_hints`）传递给 slot_filling

## Scripts
- `scripts/mock_query.py` — mock 数据查询脚本

## Output Schema

脚本输出除 `data` / `analysis` / `summary` 外，还包含 `config_hints` 块，供后续 Skill 使用：

| 字段 | 含义 | 下游用途 |
|------|------|---------|
| `config_hints.priority_pons` | CEI < 60 的问题 PON 口 | CEI/远程闭环配置目标 |
| `config_hints.watch_pons` | CEI 60-75 的观察 PON 口 | 持续监控 |
| `config_hints.distinct_issues` | 所有异常类型汇总（原始中文） | fault_config 检测规则推断 |
| `config_hints.scope_indicator` | 问题波及范围（single_pon / multi_pon / regional） | 推断 guarantee_target 槽位 |
| `config_hints.peak_time_window` | 推断的高峰时段（如 "19:00-22:00"，无则 null） | 推断 time_window 槽位 |
| `config_hints.has_complaints` | 是否存在用户投诉 | 推断 complaint_history 槽位 |
| `config_hints.remote_loop_candidates` | 建议开启自动闭环的 PON 口 | remote_loop 配置优先级 |

## Examples

**输入**: "找出 CEI 分数较低的 PON 口并分析原因"
**输出**: PON 口排名 + 异常指标 + 可能原因分析
