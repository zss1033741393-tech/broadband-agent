from __future__ import annotations

"""IntentAgent — 意图解析 + 画像补全（阶段1）"""

import json
from pathlib import Path

from agno.agent import Agent

from app.outputs.sink import output_sink_hook

from .tools import analyze_intent, discover_extra_skills, get_pipeline_file

_SKILL_REFS = Path(__file__).parent.parent.parent / "skills" / "intent_profiler" / "references"


def _build_intent_prompt() -> str:
    """动态读取 references 文件，构建含完整规范的 Prompt。

    单一来源：Prompt 内容直接来自 intent_schema.json / scene_decision_tree.md /
    field_rules.md，无需手动同步。
    """
    schema = json.loads((_SKILL_REFS / "intent_schema.json").read_text(encoding="utf-8"))
    decision_tree = (_SKILL_REFS / "scene_decision_tree.md").read_text(encoding="utf-8")
    field_rules = (_SKILL_REFS / "field_rules.md").read_text(encoding="utf-8")
    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)

    return f"""\
你是家宽 CEI 体验感知优化意图解析专家。

## 意图 JSON 规范

以下规范定义了需要提取的所有字段、枚举值和合法组合：

```json
{schema_str}
```

## {decision_tree}

## {field_rules}

## 处理流程

1. 从用户输入中尽可能多地提取信息，按规范填充 intent_goal JSON（未知字段留空）
2. 调用 `analyze_intent(intent_goal={{...}})` 执行结构/枚举/逻辑一致性校验
3. `complete=false` 时：
   - 根据 `missing_fields` 自主组织**自然语言追问**，结合用户的业务场景，不要机械列举字段名
   - 每轮最多追问 3 个字段，最多追问 3 轮
   - 追问后将用户补充信息合并到 intent_goal 中，再次调用 `analyze_intent`
4. `missing_fields` 中出现 `scenario_package_mismatch` 时：向用户解释套餐与场景的对应关系，请其确认
5. 超过 3 轮追问后仍不完整：用合理默认值补全剩余字段，告知用户，继续流程
6. `complete=true` 时：返回 2-3 句关键摘要（如"直播套餐-卖场走播，18:00-22:00，高优先，有投诉记录"），不复述完整 JSON

## 严禁事项

- 禁止跳过 `analyze_intent` 工具自行编造意图或画像数据
- 禁止在未调用工具的情况下虚构 JSON 结果
- 工具返回 `error` 时必须停止流程并将错误信息反馈给用户
- 禁止向用户展示原始 JSON 结构（摘要即可，详细数据已落盘到 outputs/）
"""


# 模块加载时构建一次，运行期不变
INTENT_PROMPT = _build_intent_prompt()


def build_intent_agent(model: object, num_history_runs: int, debug_mode: bool) -> Agent:
    """构建意图解析 Agent。"""
    return Agent(
        name="IntentAgent",
        role="意图解析与用户画像",
        model=model,
        skills=discover_extra_skills(),
        tools=[get_pipeline_file, analyze_intent],
        instructions=INTENT_PROMPT,
        add_history_to_context=True,
        num_history_runs=num_history_runs,
        tool_hooks=[output_sink_hook],
        markdown=True,
        debug_mode=debug_mode,
    )
