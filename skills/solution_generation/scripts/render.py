"""方案模板渲染脚本 — 根据用户画像渲染四类配置。

作为 agno Skill 脚本被调用。
"""

import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def render_all(profile_json: str) -> str:
    """渲染所有四类配置模板。

    Args:
        profile_json: 用户画像 JSON 字符串

    Returns:
        包含四类配置的 JSON 结果
    """
    try:
        profile = json.loads(profile_json) if isinstance(profile_json, str) else profile_json
    except json.JSONDecodeError:
        return json.dumps({"error": "无效的画像 JSON"}, ensure_ascii=False)

    # 设置默认值
    defaults = {
        "user_type": "主播用户",
        "package_type": "普通套餐",
        "scenario": "家庭直播",
        "guarantee_target": "家庭网络",
        "time_window": "全天",
        "complaint_history": False,
    }
    ctx = {**defaults, **profile}

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )

    results = {}
    templates = {
        "cei_config": "cei_spark.yaml.j2",
        "fault_config": "fault_api.json.j2",
        "remote_loop": "remote_loop.json.j2",
        "wifi_simulation": "wifi_sim.yaml.j2",
    }

    for config_name, template_file in templates.items():
        try:
            tmpl = env.get_template(template_file)
            rendered = tmpl.render(**ctx)
            results[config_name] = rendered
        except Exception as e:
            results[config_name] = f"渲染失败: {str(e)}"

    return json.dumps(results, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(render_all(sys.argv[1]))
    else:
        sample = json.dumps({
            "user_type": "主播用户",
            "package_type": "直播套餐",
            "scenario": "卖场走播",
            "guarantee_target": "STA级",
            "time_window": "18:00-22:00",
        })
        print(render_all(sample))
