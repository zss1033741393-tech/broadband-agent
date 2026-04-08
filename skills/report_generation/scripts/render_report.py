#!/usr/bin/env python3
"""报告渲染脚本 — 将分析结果或方案配置渲染为 Markdown 报告。

支持两种 CLI 调用模式：
  python render_report.py '<context_json>'          # 通用上下文模式（综合目标流程）
  python render_report.py --insight '<insight_json>'  # 数据洞察模式（接收 mock_query.py 输出）

作为 agno Skill 脚本被调用。
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader

_REFERENCES_DIR = Path(__file__).resolve().parent.parent / "references"


def render(context_json: str) -> str:
    """通用渲染入口，接收上下文 JSON，用 Jinja2 渲染 report.md.j2。

    Args:
        context_json: 上下文 JSON 字符串，支持以下键：
            - title: 报告标题（可选，默认"网络调优方案报告"）
            - timestamp: 生成时间（可选，自动填充为当前时间）
            - session_id: 会话 ID（可选）
            - profile: 用户画像 dict（综合目标流程使用）
            - configs: 方案配置 dict（综合目标流程使用）
            - verification: 校验结果 dict（可选）
            - analysis: 数据分析结果 list（数据洞察流程使用）

    Returns:
        渲染后的 Markdown 字符串；出错时返回错误描述字符串。
    """
    try:
        ctx: Dict[str, Any] = json.loads(context_json) if isinstance(context_json, str) else context_json
    except json.JSONDecodeError as exc:
        return f"渲染失败: 无效的上下文 JSON — {exc}"

    if "timestamp" not in ctx:
        ctx["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    env = Environment(
        loader=FileSystemLoader(str(_REFERENCES_DIR)),
        keep_trailing_newline=True,
    )

    try:
        tmpl = env.get_template("report.md.j2")
        return tmpl.render(**ctx)
    except Exception as exc:
        return f"渲染失败: {exc}"


def render_from_insight(insight_json: str) -> str:
    """数据洞察模式渲染入口，直接接收 mock_query.py 的完整输出。

    提取 analysis 字段并注入默认标题后调用 render()。

    Args:
        insight_json: mock_query.py 的完整 JSON 输出字符串。

    Returns:
        渲染后的 Markdown 字符串。
    """
    try:
        insight: Dict[str, Any] = json.loads(insight_json) if isinstance(insight_json, str) else insight_json
    except json.JSONDecodeError as exc:
        return f"渲染失败: 无效的 insight JSON — {exc}"

    ctx: Dict[str, Any] = {
        "title": "网络质量数据分析报告",
        "analysis": insight.get("analysis", []),
    }
    return render(json.dumps(ctx, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--insight":
        insight_input = sys.argv[2] if len(sys.argv) > 2 else "{}"
        print(render_from_insight(insight_input))
    elif len(sys.argv) > 1:
        print(render(sys.argv[1]))
    else:
        # 默认示例：输出带样例数据的报告
        sample = json.dumps(
            {
                "title": "网络质量数据分析报告（示例）",
                "analysis": [
                    {
                        "pon_port": "PON-2/0/5",
                        "cei_score": 48.9,
                        "issues": ["带宽利用率过高", "丢包率超标", "平均时延过高"],
                        "probable_causes": ["用户数(60)较多，带宽竞争激烈", "拥塞导致排队时延增加"],
                        "recommendation": "建议优先关注",
                    },
                    {
                        "pon_port": "PON-3/0/1",
                        "cei_score": 82.1,
                        "issues": [],
                        "probable_causes": [],
                        "recommendation": "状态良好",
                    },
                ],
            },
            ensure_ascii=False,
        )
        print(render(sample))
