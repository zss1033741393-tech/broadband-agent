"""共享工具函数 — 供各子 Agent 注册使用

包含：
  get_pipeline_file  — 获取上一阶段产出文件路径（缺失时报错，禁止编造）
  check_constraints  — 直接 Python 约束校验 + 自动落盘 constraint.json
  translate_configs  — 直接 Python 配置转译 + 自动落盘 configs.json
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
_OUTPUTS_ROOT = Path("outputs")


# ─────────────────────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────────────────────

def _load_script_module(relative_path: str):
    """通过 importlib 按路径加载 skills/ 下的脚本模块"""
    script_path = SKILLS_DIR / relative_path
    spec = importlib.util.spec_from_file_location("_skill_script", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _persist_stage(stage: str, payload: dict[str, Any]) -> None:
    """将阶段产出写入 outputs/{session_id}/{stage}.json"""
    sid = get_current_session_id()
    if not sid:
        logger.warning("_persist_stage: 无 session_id，跳过 %s 落盘", stage)
        return
    session_dir = _OUTPUTS_ROOT / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    out_path = session_dir / f"{stage}.json"
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("persist_stage: %s → %s", stage, out_path)


def _read_plans(plans_file: str) -> dict[str, Any] | None:
    """读取 plans.json 并转换为 {template: plan_obj} 格式。

    Returns None + 已记录错误时返回 None。
    """
    plans_path = Path(plans_file)
    if not plans_path.exists():
        return None
    raw: Any = json.loads(plans_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "plans" in raw and isinstance(raw["plans"], list):
        return {item["template"]: item for item in raw["plans"] if "template" in item}
    return raw


def _read_intent_goal() -> dict[str, Any]:
    """从当前会话的 intent.json 提取 intent_goal 字段。"""
    sid = get_current_session_id()
    if not sid:
        return {}
    intent_path = _OUTPUTS_ROOT / sid / "intent.json"
    if not intent_path.exists():
        return {}
    raw = json.loads(intent_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "intent_goal" in raw:
        return raw["intent_goal"]
    return raw if isinstance(raw, dict) else {}


# ─────────────────────────────────────────────────────────────
# 公开工具函数
# ─────────────────────────────────────────────────────────────

def get_pipeline_file(stage: str) -> str:
    """获取本会话某阶段产出文件的路径。

    stage 可选值：intent / plans / constraint / configs
    注意：profile 数据包含在 intent.json 的 "profile" 字段中，不是独立文件。

    重要：如果返回 error，你必须停止当前流程并将错误信息反馈给用户，
    不得跳过或自行编造数据继续执行。

    Returns:
        文件路径字符串（如 "outputs/abc123/plans.json"）
        或包含 error 字段的 JSON 字符串（文件不存在时）
    """
    valid_stages = {"intent", "plans", "constraint", "configs"}
    if stage not in valid_stages:
        return json.dumps({
            "error": f"无效的 stage '{stage}'，合法值为：{', '.join(sorted(valid_stages))}。"
                     "profile 数据在 intent.json 的 'profile' 字段中，请使用 stage='intent'。"
        }, ensure_ascii=False)

    sid = get_current_session_id()
    if not sid:
        return json.dumps({
            "error": "当前会话无阶段产出。这说明前序阶段未正确执行，"
                     "请停止当前操作并告知用户检查流程。"
        }, ensure_ascii=False)

    path = Path(f"outputs/{sid}/{stage}.json")
    if not path.exists():
        return json.dumps({
            "error": f"文件不存在: {path}。前序阶段 '{stage}' 的产出未生成，"
                     "请停止当前操作并告知用户：上一阶段可能执行失败，需要检查。"
        }, ensure_ascii=False)
    return str(path)


def check_constraints(
    plans_file: str, intent_goal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行约束校验（直接调用规则引擎）。

    结果自动写入 outputs/{session_id}/constraint.json。

    Args:
        plans_file: plans.json 文件路径，由 get_pipeline_file("plans") 获取。
                    如果文件不存在，你必须停止并报告错误，不得编造方案数据。
        intent_goal: 意图目标 dict（可省略，工具自动从 intent.json 读取）

    Returns:
        {passed, conflicts, warnings, failed_checks, suggestions}
    """
    if cfg.pipeline.use_llm_constraint:
        return {"error": "LLM 约束校验尚未实现，请将 use_llm_constraint 保持 false"}

    plans = _read_plans(plans_file)
    if plans is None:
        return {
            "error": f"文件不存在: {plans_file}。请停止并告知用户：plan_generator 阶段未生成方案文件。"
        }

    if intent_goal is None:
        intent_goal = _read_intent_goal()

    validate_mod = _load_script_module("constraint_checker/scripts/validate.py")
    result: dict[str, Any] = validate_mod.run_all_checks(plans, intent_goal)

    # 自动落盘 constraint.json
    _persist_stage("constraint", result)
    return result


def translate_configs(
    plans_file: str, device_id: str = "",
) -> dict[str, Any]:
    """执行配置转译（直接调用字段映射引擎）。

    结果自动写入 outputs/{session_id}/configs.json。

    Args:
        plans_file: plans.json 文件路径，由 get_pipeline_file("plans") 获取。
                    如果文件不存在，你必须停止并报告错误，不得编造配置数据。
        device_id: 目标设备 ID（可选，默认为空字符串）

    Returns:
        {configs, success, failed_fields, schema}
    """
    if cfg.pipeline.use_llm_translation:
        return {"error": "LLM 配置转译尚未实现，请将 use_llm_translation 保持 false"}

    plans = _read_plans(plans_file)
    if plans is None:
        return {
            "error": f"文件不存在: {plans_file}。请停止并告知用户：plan_generator 阶段未生成方案文件。"
        }

    translate_mod = _load_script_module("config_translator/scripts/translate.py")
    result: dict[str, Any] = translate_mod.translate_all_plans(plans, device_id)
    result["schema"] = translate_mod.load_config_schema()

    # 自动落盘 configs.json
    _persist_stage("configs", result)
    return result
