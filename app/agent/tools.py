"""共享工具函数 — 供各子 Agent 注册使用

调用链路（sync 全程，无 async）：
  Gradio async → Agno arun(async) → run_in_executor → 工具函数(sync)
  Agno 在 async 环境中通过线程池执行 sync 工具，工具内部禁止调用 asyncio.run()。

工具清单（全部 sync def，Agno 自动线程池调度）：
  get_pipeline_file  — 获取上一阶段产出文件路径
  analyze_intent     — 意图解析 + 画像补全 → intent.json
  generate_plans     — 五大方案并行填充   → plans.json
  check_constraints  — 规则引擎约束校验   → constraint.json
  translate_configs  — 字段映射配置转译   → configs.json

落盘：每个工具调用后自动写入 outputs/{session_id}/{stage}.json。
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


def analyze_intent(
    intent_goal: dict[str, Any],
) -> dict[str, Any]:
    """执行意图解析与画像补全。

    根据用户输入的意图字段，加载画像模板，推断补全缺失字段，校验完整性。
    结果自动写入 outputs/{session_id}/intent.json。

    Args:
        intent_goal: 从用户输入中提取的意图字段 dict，例如：
            {
                "user_type": "直播用户",
                "scenario": "上行带宽保障",
                "guarantee_target": {"sensitivity": "卡顿", "priority_level": "high"},
                "guarantee_period": {"start_time": "20:00", "end_time": "00:00"}
            }

    Returns:
        {complete, intent_goal, profile, missing_fields, followup, schema}
        - complete=true 时意图完整，可进入下一阶段
        - complete=false 时需根据 followup 追问用户
    """
    analyze_mod = _load_script_module("intent_profiler/scripts/analyze.py")

    # 1. 加载画像模板，用已知意图字段填充
    profile = analyze_mod.load_profile_template()
    profile["user_profile"].update(
        {k: v for k, v in intent_goal.items() if v}
    )

    # 2. 将画像推断结果合并回意图
    intent_goal = analyze_mod.merge_intent_with_profile(intent_goal, profile)

    # 3. 校验意图完整性
    complete, missing = analyze_mod.validate_intent(intent_goal)
    followup = analyze_mod.generate_followup_questions(missing) if not complete else ""
    schema = analyze_mod.load_intent_schema()

    result: dict[str, Any] = {
        "complete": complete,
        "intent_goal": intent_goal,
        "profile": profile,
        "missing_fields": missing,
        "followup": followup,
        "schema": schema,
    }
    _persist_stage("intent", result)
    return result


def generate_plans(
    intent_file: str = "",
) -> dict[str, Any]:
    """执行方案生成（直接调用模板填充引擎）。

    自动读取 intent.json 中的 intent_goal，填充五大方案模板。
    结果自动写入 outputs/{session_id}/plans.json。

    Args:
        intent_file: intent.json 文件路径（可省略，自动从当前会话读取）。
                     推荐用法：先调用 get_pipeline_file("intent") 获取路径再传入。

    Returns:
        {plans, rules} 或 {error}
    """
    # 读取 intent_goal
    if intent_file:
        intent_path = Path(intent_file)
        if not intent_path.exists():
            return {
                "error": f"文件不存在: {intent_file}。请停止并告知用户：intent 阶段未生成产出文件。"
            }
        try:
            raw = json.loads(intent_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"error": f"文件格式错误: {intent_file}，无法解析 JSON。"}
        if isinstance(raw, dict) and "intent_goal" in raw:
            intent_goal = raw["intent_goal"]
        else:
            intent_goal = raw if isinstance(raw, dict) else {}
    else:
        intent_goal = _read_intent_goal()

    if not intent_goal:
        return {
            "error": "无法读取 intent_goal，请确保意图解析阶段已完成且 intent.json 存在。"
        }

    generate_mod = _load_script_module("plan_generator/scripts/generate.py")
    # 线程池并行填充 5 个模板（不用 asyncio.run，避免 event loop ���突）
    from concurrent.futures import ThreadPoolExecutor

    def _fill_one(tpl_name: str) -> dict[str, Any]:
        template = generate_mod.load_template(tpl_name)
        params = generate_mod.build_params_from_intent(intent_goal, tpl_name)
        filled, changes = generate_mod.fill_template(template, params)
        return {
            "plan_name": template.get("plan_name", tpl_name),
            "template": tpl_name,
            "filled_data": filled,
            "changes": changes,
            "status": "filled",
        }

    with ThreadPoolExecutor(max_workers=len(generate_mod.TEMPLATE_FILES)) as pool:
        results = list(pool.map(_fill_one, generate_mod.TEMPLATE_FILES))
    rules = generate_mod.load_filling_rules()

    result: dict[str, Any] = {"plans": results, "rules": rules[:500]}
    _persist_stage("plans", result)
    return result


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
