---
name: report_rendering
description: "报告渲染：把 InsightAgent 的执行产物（多阶段或归因形态）渲染为结构化 Markdown 报告"
---

# 报告渲染

## Metadata
- **paradigm**: Generator (纯模板填空)
- **when_to_use**: InsightAgent 完成所有 Phase 执行后，需要汇总 Markdown 报告
- **inputs**: 上下文 JSON — 两种形态自动识别
- **outputs**: 结构化 Markdown 报告（stdout 即最终产物，原样输出）

## 使用范围

- ✅ InsightAgent 阶段 5 — 多阶段洞察报告生成（新形态）
- ✅ InsightAgent 归因形态报告（旧形态，向后兼容）
- ❌ Provisioning 执行报告（Provisioning 直接透传 Skill stdout，不经过本 Skill）
- ❌ 综合目标方案报告（方案由 Orchestrator 汇总派发结果）

## 两种上下文形态

脚本自动根据 context JSON 的键选择模板：

### A. 多阶段形态（新，优先匹配）— 含 `phases` 键
```json
{
  "title": "网络质量数据洞察报告",
  "goal": "...",
  "summary": { ... summary JSON（见 prompts/insight.md §8） ... },
  "phases": [
    {
      "phase_id": 1,
      "name": "...",
      "milestone": "...",
      "table_level": "day",
      "focus_dimensions": [],
      "steps": [
        {
          "step_id": 1,
          "insight_type": "OutstandingMin",
          "significance": 0.73,
          "description": "...",
          "rationale": "...",
          "found_entities": {"portUuid": ["..."]},
          "fix_warnings": []
        }
      ],
      "reflection": {"choice": "A", "reason": "..."}
    }
  ],
  "conclusion": "..."
}
```
→ 使用 `references/multi_phase_report.md.j2`

### B. 归因形态（旧，向后兼容）— 含 `analysis` 键
```json
{
  "title": "...",
  "summary": {...},
  "analysis": [{"pon_port": "...", "issues": [...], ...}]
}
```
→ 使用 `references/report.md.j2`

## How to Use

1. 按上下文形态构建 JSON
2. 调用脚本：
   ```
   get_skill_script(
       "report_rendering",
       "render_report.py",
       execute=True,
       args=["<context_json_string>"]
   )
   ```
3. 脚本根据 `phases` 键是否存在选模板渲染，**stdout 即最终报告**
4. Agent **必须原样输出 stdout**，不得二次改写

## Scripts

- `scripts/render_report.py` — Jinja2 渲染脚本（自动识别上下文形态 → 选模板）

## References

- `references/report.md.j2` — 归因形态模板（旧，按 PON 口列分析段）
- `references/multi_phase_report.md.j2` — 多阶段形态模板（新，按 Phase → Step 结构渲染）

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
