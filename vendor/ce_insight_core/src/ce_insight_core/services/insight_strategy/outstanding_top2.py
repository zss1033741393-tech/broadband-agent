"""
Top2 突出分析：找出前两名与其余分组的差距，评估头部集中度。
"""

import pandas as pd
import numpy as np
from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy


class OutstandingTop2Strategy(InsightStrategy):

    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        group_column: str = kwargs.get("group_column", "")
        col = value_columns[0]

        grouped = self._df.groupby(group_column)[col].mean().dropna()

        if len(grouped) < 2:
            self._description = "分组数不足（<2），无法进行 Top2 分析"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        sorted_vals = grouped.sort_values(ascending=False)
        top2 = sorted_vals.iloc[:2]
        rest = sorted_vals.iloc[2:]

        top2_mean = float(top2.mean())
        rest_mean = float(rest.mean())
        overall_mean = float(grouped.mean())
        gap = top2_mean - rest_mean

        # 集中度：前两名占总和的比例
        total = float(grouped.sum())
        top2_share = float(top2.sum()) / total if total > 0 else 0

        result_df = sorted_vals.reset_index()
        result_df.columns = [group_column, col]
        result_df["is_top2"] = [True, True] + [False] * len(rest)
        self._filter_data = result_df

        top2_names = ", ".join(top2.index.astype(str).tolist())
        self._description = {
            "top2_groups": top2.index.tolist(),
            "top2_mean": round(top2_mean, 2),
            "rest_mean": round(rest_mean, 2),
            "gap": round(gap, 2),
            "top2_share": round(top2_share, 4),
            "summary": f"前两名 ({top2_names}) 均值 {top2_mean:.2f}，"
                       f"领先其余 {gap:.2f}，占总量 {top2_share:.1%}",
        }

        # 头部集中越高越显著
        self._significance_score = float(np.clip(top2_share, 0, 1))

        from ce_insight_core.services.insight_strategy.chart_style import (
            truncate_labels, base_grid, base_title, base_tooltip,
            rotated_axis_label, BLUE, HIGHLIGHT_RED,
        )
        top_n = 10
        display_df = result_df.head(top_n)
        display_labels = truncate_labels(display_df[group_column].astype(str).tolist())
        colors = [HIGHLIGHT_RED if t else BLUE for t in display_df["is_top2"]]
        self._chart_configs = {
            "chart_type": "bar",
            "title": base_title(f"{col} Top2 突出分析"),
            "tooltip": base_tooltip("axis"),
            "grid": base_grid(),
            "xAxis": {"type": "category", "data": display_labels,
                      "axisLabel": rotated_axis_label(30)},
            "yAxis": {"type": "value", "name": col, "nameTextStyle": {"fontSize": 11}},
            "series": [{
                "type": "bar",
                "data": [{"value": round(v, 2), "itemStyle": {"color": c}}
                         for v, c in zip(display_df[col].tolist(), colors)],
                "barMaxWidth": 40,
            }],
        }
