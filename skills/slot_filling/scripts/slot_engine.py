#!/usr/bin/env python3
"""槽位填充引擎 — 读取 slot_schema.yaml 驱动追问逻辑。

作为 agno Skill 脚本被调用。接受 JSON 输入，返回槽位状态与追问提示。
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "configs" / "slot_schema.yaml"


def load_schema() -> Dict[str, Any]:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_missing_slots(schema: Dict, current_state: Dict) -> List[str]:
    """按 schema 定义顺序，返回尚未填充的必填槽位列表。"""
    slots_def = schema.get("slots", {})
    missing = []
    for slot_name, slot_cfg in slots_def.items():
        if slot_cfg.get("required", False) and current_state.get(slot_name) is None:
            missing.append(slot_name)
    return missing


def get_next_questions(schema: Dict, current_state: Dict, max_questions: int = 2) -> List[Dict[str, str]]:
    """返回下一批需要追问的槽位信息。"""
    slots_def = schema.get("slots", {})
    missing = get_missing_slots(schema, current_state)
    questions = []

    for slot_name in missing[:max_questions]:
        slot_cfg = slots_def[slot_name]
        prompt = slot_cfg.get("prompt", f"请提供 {slot_name}")

        # 如果有依赖分支，根据当前状态调整选项
        if "depends_on" in slot_cfg and "branches" in slot_cfg:
            dep_value = current_state.get(slot_cfg["depends_on"])
            if dep_value and dep_value in slot_cfg["branches"]:
                options = slot_cfg["branches"][dep_value]
                prompt = f"{prompt}（可选: {' / '.join(options)}）"
        elif "enum" in slot_cfg:
            options = slot_cfg["enum"]
            prompt = f"请选择{slot_name}（{' / '.join(options)}）"

        questions.append({
            "slot_name": slot_name,
            "prompt": prompt,
            "required": slot_cfg.get("required", False),
            "type": slot_cfg.get("type", "enum"),
        })

    return questions


def parse_user_input(user_text: str, schema: Dict, current_state: Dict) -> Dict[str, Any]:
    """尝试从用户文本中提取槽位值。"""
    slots_def = schema.get("slots", {})
    extracted = {}
    # 合并已知状态，以便依赖字段能在同一轮解析中使用
    merged = {**current_state}

    for slot_name, slot_cfg in slots_def.items():
        if merged.get(slot_name) is not None:
            continue

        if "enum" in slot_cfg:
            for option in slot_cfg["enum"]:
                if option in user_text:
                    extracted[slot_name] = option
                    merged[slot_name] = option
                    break

        if "branches" in slot_cfg:
            dep_value = merged.get(slot_cfg.get("depends_on", ""))
            if dep_value and dep_value in slot_cfg["branches"]:
                for option in slot_cfg["branches"][dep_value]:
                    if option in user_text:
                        extracted[slot_name] = option
                        merged[slot_name] = option
                        break

        if slot_cfg.get("type") == "string" and slot_name == "time_window":
            import re
            time_pattern = r'\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}'
            match = re.search(time_pattern, user_text)
            if match:
                extracted[slot_name] = match.group().replace('–', '-')
            elif "全天" in user_text:
                extracted[slot_name] = "全天"

        if slot_cfg.get("type") == "bool" and slot_name == "complaint_history":
            if "投诉" in user_text or "有投诉" in user_text:
                extracted[slot_name] = True
            elif "无投诉" in user_text or "没有投诉" in user_text:
                extracted[slot_name] = False

    return extracted


def process(current_state_json: str = "{}", user_input: str = "") -> str:
    """主处理函数 — 被 agno skill script 机制调用。

    Args:
        current_state_json: 当前槽位状态 JSON
        user_input: 用户最新输入

    Returns:
        JSON 字符串，包含更新后的状态、是否完成、追问列表
    """
    schema = load_schema()

    try:
        current_state = json.loads(current_state_json) if current_state_json else {}
    except json.JSONDecodeError:
        current_state = {}

    # 从用户输入中提取槽位值
    if user_input:
        extracted = parse_user_input(user_input, schema, current_state)
        current_state.update(extracted)

    # 检查是否完成
    missing = get_missing_slots(schema, current_state)
    is_complete = len(missing) == 0

    # 获取追问
    questions = get_next_questions(schema, current_state) if not is_complete else []

    result = {
        "state": current_state,
        "is_complete": is_complete,
        "missing_slots": missing,
        "next_questions": questions,
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 支持命令行调用测试
    state = "{}"
    user_input = ""
    if len(sys.argv) > 1:
        user_input = sys.argv[1]
    if len(sys.argv) > 2:
        state = sys.argv[2]
    print(process(state, user_input))
