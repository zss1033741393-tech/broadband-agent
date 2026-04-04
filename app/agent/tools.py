"""共享工具函数 — 供各子 Agent 注册使用

包含：
  get_pipeline_file  — 获取上一阶段产出文件路径（避免内联 JSON 浪费 token）
  check_constraints  — 直接 Python 约束校验（无 subprocess 开销）
  translate_configs  — 直接 Python 配置转译（无 subprocess 开销）
"""
from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

from app.config import load_config
from app.outputs.sink import get_current_session_id

logger = logging.getLogger("agent.tools")

cfg = load_config()
SKILLS_DIR = Path(cfg.pipeline.skills_dir).resolve()


# ─────────────────────────────────────────────────────────────
# 内部工具：按路径加载脚本模块（避免修改 sys.path）
# ─────────────────────────────────────────────────────────────

def _load_script_module(relative_path: str):
    """通过 importlib 按路径加载 skills/ 下的脚本模块"""
    script_path = SKILLS_DIR / relative_path
    spec = importlib.util.spec_from_file_location("_skill_script", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ─────────────────────────────────────────────────────────────
# 公开工具函数
# ─────────────────────────────────────────────────────────────

def get_pipeline_file(stage: str) -> str:
    """获取本会话某阶段产出文件的路径。

    stage 可选值：intent / profile / plans / constraint / configs

    在调用下一阶段脚本前，先调用此工具获取上一阶段产出路径，
    再以 --xxx-file <path> 参数传给脚本，脚本从磁盘读取，
    避免将完整 JSON 内联到 args 中浪费 token。

    Returns:
        文件路径字符串（如 "outputs/abc123/plans.json"）
        或包含 error 字段的 JSON 字符串（文件不存在时）
    """
    sid = get_current_session_id()
    if not sid:
        return '{"error": "当前会话无阶段产出，请先执行对应阶段脚本"}'
    path = Path(f"outputs/{sid}/{stage}.json")
    if not path.exists():
        return f'{{"error": "文件不存在: {path}，请先执行上一阶段脚本"}}'
    return str(path)


def check_constraints(plans_file: str, intent_goal: dict[str, Any] | None = None) -> dict[str, Any]:
    """执行约束校验（直接调用规则引擎，无 subprocess 开销）。

    Args:
        plans_file: plans.json 文件路径，由 get_pipeline_file("plans") 获取
        intent_goal: 意图目标 dict（可省略，工具自动从 intent.json 读取）

    Returns:
        {passed, conflicts, warnings, failed_checks, suggestions}
    """
    if cfg.pipeline.use_llm_constraint:
        return {"error": "LLM 约束校验尚未实现，请将 use_llm_constraint 保持 false"}

    plans_path = Path(plans_file)
    if not plans_path.exists():
        return {"error": f"文件不存在: {plans_file}，请先执行 plan_generator 阶段"}

    raw_plans: Any = json.loads(plans_path.read_text(encoding="utf-8"))
    if isinstance(raw_plans, dict) and "plans" in raw_plans and isinstance(raw_plans["plans"], list):
        plans: dict[str, Any] = {
            item["template"]: item for item in raw_plans["plans"] if "template" in item
        }
    else:
        plans = raw_plans

    if intent_goal is None:
        sid = get_current_session_id()
        if sid:
            intent_path = Path(f"outputs/{sid}/intent.json")
            if intent_path.exists():
                intent_goal = json.loads(intent_path.read_text(encoding="utf-8"))
    if intent_goal is None:
        intent_goal = {}

    validate_mod = _load_script_module("constraint_checker/scripts/validate.py")
    return validate_mod.run_all_checks(plans, intent_goal)


def translate_configs(plans_file: str, device_id: str = "") -> dict[str, Any]:
    """执行配置转译（直接调用字段映射引擎，无 subprocess 开销）。

    Args:
        plans_file: plans.json 文件路径，由 get_pipeline_file("plans") 获取
        device_id: 目标设备 ID（可选，默认为空字符串）

    Returns:
        {configs, success, failed_fields, schema}
    """
    if cfg.pipeline.use_llm_translation:
        return {"error": "LLM 配置转译尚未实现，请将 use_llm_translation 保持 false"}

    plans_path = Path(plans_file)
    if not plans_path.exists():
        return {"error": f"文件不存在: {plans_file}，请先执行 plan_generator 阶段"}

    raw_plans: Any = json.loads(plans_path.read_text(encoding="utf-8"))
    if isinstance(raw_plans, dict) and "plans" in raw_plans and isinstance(raw_plans["plans"], list):
        plans: dict[str, Any] = {
            item["template"]: item for item in raw_plans["plans"] if "template" in item
        }
    else:
        plans = raw_plans

    translate_mod = _load_script_module("config_translator/scripts/translate.py")
    result: dict[str, Any] = translate_mod.translate_all_plans(plans, device_id)
    result["schema"] = translate_mod.load_config_schema()
    return result
