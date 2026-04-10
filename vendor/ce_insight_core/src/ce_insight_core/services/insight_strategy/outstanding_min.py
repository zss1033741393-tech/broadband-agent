"""
突出最小值：找出各分组中指标值最低的分组，评估其突出程度。
"""

import pandas as pd
import numpy as np
from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy


class OutstandingMinStrategy(InsightStrategy):

    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        group_column: str = kwargs.get("group_column", "")
        col = value_columns[0]

        grouped = self._df.groupby(group_column)[col].mean().dropna()

        if len(grouped) < 2:
            self._description = "分组数不足"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        sorted_vals = grouped.sort_values(ascending=True)
        min_group = sorted_vals.index[0]
        min_val = float(sorted_vals.iloc[0])
        second_val = float(sorted_vals.iloc[1])
        overall_mean = float(grouped.mean())
        std_val = float(grouped.std())

        gap = second_val - min_val
        z_score = (overall_mean - min_val) / std_val if std_val > 0 else 0

        result_df = sorted_vals.reset_index()
        result_df.columns = [group_column, col]
        self._filter_data = result_df

        self._description = {
            "min_group": str(min_group),
            "min_value": round(min_val, 2),
            "second_value": round(second_val, 2),
            "gap": round(gap, 2),
            "z_score": round(float(z_score), 4),
            "summary": f"{col} 最小值出现在 {min_group}（{min_val:.2f}），"
                       f"低于第二名 {gap:.2f}，z-score={z_score:.2f}",
        }
        self._significance_score = float(np.clip(abs(z_score) / 3, 0, 1))

        labels = result_df[group_column].astype(str).tolist()
        from ce_insight_core.services.insight_strategy.chart_style import (
            truncate_labels, base_grid, base_title, base_tooltip,
            rotated_axis_label, BLUE, HIGHLIGHT_RED,
        )
        top_n = 10
        display_df = result_df.head(top_n)
        display_labels = truncate_labels(display_df[group_column].astype(str).tolist())
        display_vals = display_df[col].round(2).tolist()
        colors = [HIGHLIGHT_RED if i == 0 else BLUE for i in range(len(display_vals))]
        self._chart_configs = {
            "chart_type": "bar",
            "title": base_title(f"{col} 最小值分析 (Top{min(top_n, len(result_df))})"),
            "tooltip": base_tooltip("axis"),
            "grid": base_grid(),
            "xAxis": {"type": "category", "data": display_labels,
                      "axisLabel": rotated_axis_label(30)},
            "yAxis": {"type": "value", "name": col, "nameTextStyle": {"fontSize": 11}},
            "series": [{
                "type": "bar",
                "data": [{"value": v, "itemStyle": {"color": c}} for v, c in zip(display_vals, colors)],
                "barMaxWidth": 40,
            }],
        }
