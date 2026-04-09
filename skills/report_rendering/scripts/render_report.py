#!/usr/bin/env python3
"""报告渲染脚本 — 将 InsightAgent 的查询/归因结果渲染为 Markdown 报告。

作为 agno Skill 脚本被调用。stdout 即最终产物，Agent 必须原样输出。
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader

_REFERENCES_DIR = Path(__file__).resolve().parents[1] / "references"


def render(context_json: str) -> str:
    """渲染 Markdown 报告。

    Args:
        context_json: 上下文 JSON 字符串，支持字段：
            - title: 报告标题（可选）
            - timestamp: 生成时间（可选，自动填充）
            - summary: 数据洞察摘要 dict
            - analysis: 分 PON 归因分析列表
    """
    try:
        ctx: Dict[str, Any] = (
            json.loads(context_json) if isinstance(context_json, str) else context_json
        )
    except json.JSONDecodeError as exc:
        return f"渲染失败: 无效的上下文 JSON — {exc}"

    ctx.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    env = Environment(
        loader=FileSystemLoader(str(_REFERENCES_DIR)),
        keep_trailing_newline=True,
    )
    try:
        tmpl = env.get_template("report.md.j2")
        return tmpl.render(**ctx)
    except Exception as exc:
        return f"渲染失败: {exc}"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(render(sys.argv[1]))
    else:
        sample = json.dumps(
            {
                "title": "网络质量数据洞察报告（示例）",
                "summary": {
                    "priority_pons": ["PON-2/0/5"],
                    "watch_pons": ["PON-1/0/1"],
                    "distinct_issues": ["带宽利用率过高", "丢包率超标"],
                    "scope_indicator": "regional",
                    "peak_time_window": "19:00-22:00",
                    "total_complaints_7d": 12,
                    "remote_loop_candidates": ["PON-2/0/5"],
                },
                "analysis": [
                    {
                        "pon_port": "PON-2/0/5",
                        "cei_score": 48.9,
                        "issues": ["带宽利用率过高", "丢包率超标"],
                        "probable_causes": ["用户数 60 较多，带宽竞争激烈"],
                        "recommendation": "建议优先关注",
                    }
                ],
            },
            ensure_ascii=False,
        )
        print(render(sample))
