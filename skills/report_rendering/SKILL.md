---
name: report_rendering
description: "报告渲染：将 InsightAgent 的查询+归因结果渲染为结构化 Markdown 分析报告"
---

# 报告渲染

## Metadata
- **paradigm**: Generator (纯模板填空)
- **when_to_use**: InsightAgent 完成阶段 2-3 的数据查询和归因后，需要输出 Markdown 汇总报告
- **inputs**: 上下文 JSON（`{title, summary, analysis, echarts_option?}`）
- **outputs**: 结构化 Markdown 报告（stdout 即最终产物，原样输出）

## 使用范围

- ✅ InsightAgent 阶段 4 — 洞察报告生成
- ❌ Provisioning 执行报告（Provisioning 直接透传 Skill stdout，不需要本 Skill 统一渲染）
- ❌ 综合目标方案报告（方案由 Orchestrator 汇总派发结果，不经过本 Skill）

## How to Use

1. 构建上下文 JSON：
   ```json
   {
     "title": "网络质量数据洞察报告",
     "summary": { ... 来自 data_insight 的 summary 块 ... },
     "analysis": [ ... 来自 data_insight attribution 阶段的 analysis ... ]
   }
   ```
2. 调用脚本：
   ```
   get_skill_script(
       "report_rendering",
       "render_report.py",
       execute=True,
       args=["<context_json_string>"]
   )
   ```
3. 脚本读取 `references/report.md.j2` 渲染 Markdown，**stdout 即最终报告**
4. Agent **必须原样输出 stdout**，不得二次改写

## Scripts

- `scripts/render_report.py` — Jinja2 渲染脚本

## References

- `references/report.md.j2` — 洞察报告 Jinja2 模板

## Examples

**输入**:
```json
{
  "title": "网络质量数据洞察报告",
  "summary": {
    "priority_pons": ["PON-2/0/5"],
    "distinct_issues": ["带宽利用率过高", "丢包率超标"],
    "scope_indicator": "regional"
  },
  "analysis": [
    {
      "pon_port": "PON-2/0/5",
      "cei_score": 48.9,
      "issues": ["带宽利用率过高", "丢包率超标"],
      "probable_causes": ["用户数过多"],
      "recommendation": "建议优先关注"
    }
  ]
}
```

**输出**: Markdown 报告（包含摘要表 + 分 PON 分析段）

## 禁止事项

- ❌ 不得对 stdout 进行二次改写、摘要或重排版
- ❌ 不在本 Skill 里承担综合目标方案的报告渲染（另有 Provisioning 透传）
