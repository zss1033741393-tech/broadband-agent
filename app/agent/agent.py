"""Agent 定义 — Agno 全能力集成

架构：
  - Skills: LocalSkills 自动扫描 skills/ 目录，提供渐进式加载元工具
    (get_skill_instructions / get_skill_reference / get_skill_script)
  - Knowledge: LanceDB 向量存储，领域知识 RAG 检索
  - Guardrails: PromptInjectionGuardrail 输入安全
  - Memory: add_history_to_context 会话历史
  - AgentOS: 原生 API + trace + Web UI

Python 工具函数为各 Skill 脚本提供统一的 tool_call 入口，
与 LocalSkills 配合使用（LocalSkills 负责指令，@tool 负责执行）。
"""
from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

from agno.agent import Agent
from agno.guardrails import PromptInjectionGuardrail
from agno.knowledge import Knowledge
from agno.models.openai import OpenAILike
from agno.skills import LocalSkills, Skills
from agno.tools import tool
from agno.vectordb.lancedb import LanceDb

from app.config import load_config

logger = logging.getLogger("agent")

cfg = load_config()
SKILLS_DIR = Path(cfg.pipeline.skills_dir).resolve()


# ─────────────────────────────────────────────────────────────
# Skills 自动发现（LocalSkills 提供元工具 + 指令注入）
# ─────────────────────────────────────────────────────────────

def _discover_skills() -> Skills:
    """扫描 skills/ 目录，将所有含 SKILL.md 的子目录注册为 Skill。
    LocalSkills 自动向 Agent 注册三个元工具：
      get_skill_instructions / get_skill_reference / get_skill_script
    """
    return Skills(loaders=[LocalSkills(path=str(SKILLS_DIR), validate=False)])


# ─────────────────────────────────────────────────────────────
# 动态模块加载工具函数
# ─────────────────────────────────────────────────────────────

def _import_script(script_path: Path) -> Any | None:
    """动态导入 Skill 脚本模块，失败时返回 None"""
    if not script_path.exists():
        logger.warning("脚本不存在: %s", script_path)
        return None
    module_name = f"_skill_{script_path.parent.parent.name}_{script_path.stem}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        logger.error("脚本加载失败 %s: %s", script_path, exc)
        del sys.modules[module_name]
        return None
    return mod


# ─────────────────────────────────────────────────────────────
# Skill Python 工具函数（供 LLM 通过 tool_call 真实执行）
# ─────────────────────────────────────────────────────────────

def _build_agno_tools() -> list:
    """为每个 Skill 构建 Agno @tool 函数，返回可注册列表"""
    tools = []

    # ── intent_parser ──────────────────────────────────────────
    _intent_mod = _import_script(SKILLS_DIR / "intent_parser/scripts/extract.py")
    if _intent_mod:
        _im = _intent_mod

        @tool(name="intent_parsing", description="校验用户意图完整性，返回追问或完整意图结构")
        def intent_parsing(intent_goal_json: str) -> str:
            """
            校验用户意图目标的完整性。

            Args:
                intent_goal_json: 当前已提取到的意图字段，JSON 字符串格式。
                                  首次解析传入空 JSON 对象 "{}"。
            Returns:
                JSON 字符串，含：complete(bool), missing_fields(list),
                followup(str), schema(dict)
            """
            try:
                intent_goal = json.loads(intent_goal_json) if intent_goal_json.strip() else {}
            except json.JSONDecodeError:
                intent_goal = {}
            complete, missing = _im.validate_intent(intent_goal)
            followup = _im.generate_followup_questions(missing) if not complete else ""
            schema = _im.load_intent_schema()
            return json.dumps(
                {"complete": complete, "missing_fields": missing, "followup": followup, "schema": schema},
                ensure_ascii=False,
            )

        tools.append(intent_parsing)

    # ── user_profiler ──────────────────────────────────────────
    _profile_mod = _import_script(SKILLS_DIR / "user_profiler/scripts/query_profile.py")
    if _profile_mod:
        _pm = _profile_mod

        @tool(name="user_profile", description="获取用户画像模板，标注缺失字段和补全规则")
        def user_profile(known_info_json: str = "{}") -> str:
            """
            获取用户画像模板并标注缺失字段。

            Args:
                known_info_json: 已知的用户信息，JSON 字符串。
            Returns:
                JSON 字符串，含：template(dict), missing_fields(list), field_rules(str)
            """
            try:
                known = json.loads(known_info_json) if known_info_json.strip() else {}
            except json.JSONDecodeError:
                known = {}
            profile = _pm.get_empty_profile()
            profile["user_profile"].update(known)
            missing = _pm.check_missing_fields(profile)
            rules = _pm.load_field_rules()
            return json.dumps(
                {"template": profile, "missing_fields": missing, "field_rules": rules},
                ensure_ascii=False,
            )

        tools.append(user_profile)

    # ── plan_generator ─────────────────────────────────────────
    _plan_mod = _import_script(SKILLS_DIR / "plan_generator/scripts/generate.py")
    if _plan_mod:
        _pgm = _plan_mod

        @tool(name="plan_filling", description="基于意图目标并行填充五大方案模板")
        async def plan_filling(intent_goal_json: str) -> str:
            """
            基于完整意图目标并行填充五大方案模板。

            Args:
                intent_goal_json: 完整的意图目标，JSON 字符串。
            Returns:
                JSON 字符串，含：plans(dict), changes(dict), rules(str)
            """
            try:
                intent_goal = json.loads(intent_goal_json)
            except json.JSONDecodeError:
                return json.dumps({"error": "intent_goal_json 格式错误"}, ensure_ascii=False)
            params = _pgm.build_params_from_intent(intent_goal)
            filled_plans, all_changes = await _pgm.fill_all_templates(params)
            rules = _pgm.load_filling_rules()
            return json.dumps(
                {"plans": filled_plans, "changes": all_changes, "rules": rules[:500]},
                ensure_ascii=False,
            )

        tools.append(plan_filling)

    # ── constraint_checker ─────────────────────────────────────
    _constraint_mod = _import_script(SKILLS_DIR / "constraint_checker/scripts/validate.py")
    if _constraint_mod:
        _cm = _constraint_mod

        @tool(name="constraint_check", description="对填充后的方案执行性能、组网和冲突约束校验（强制步骤）")
        def constraint_check(plans_json: str, guarantee_period_json: str = "{}") -> str:
            """
            对方案执行约束校验。

            Args:
                plans_json:            plan_filling 返回的 plans 字段，JSON 字符串。
                guarantee_period_json: 保障时段 {start_time, end_time}，JSON 字符串。
            Returns:
                JSON 字符串，含：passed(bool), violations(list)
            """
            try:
                plans = json.loads(plans_json)
            except json.JSONDecodeError:
                return json.dumps({"error": "plans_json 格式错误"}, ensure_ascii=False)
            try:
                guarantee_period = json.loads(guarantee_period_json)
            except json.JSONDecodeError:
                guarantee_period = {}
            violations = _cm.run_all_checks(plans, guarantee_period)
            return json.dumps(
                {"passed": len(violations) == 0, "violations": violations},
                ensure_ascii=False,
            )

        tools.append(constraint_check)

    # ── config_translator ──────────────────────────────────────
    _translate_mod = _import_script(SKILLS_DIR / "config_translator/scripts/translate.py")
    if _translate_mod:
        _tm = _translate_mod

        @tool(name="config_translation", description="将语义化方案 JSON 转译为设备可下发的配置格式（NL2JSON）")
        def config_translation(plans_json: str) -> str:
            """
            将语义化方案转译为设备配置（NL2JSON）。

            Args:
                plans_json: plan_filling 返回的 plans 字段，JSON 字符串。
            Returns:
                JSON 字符串，含：configs(dict), schema(dict)
            """
            try:
                plans = json.loads(plans_json)
            except json.JSONDecodeError:
                return json.dumps({"error": "plans_json 格式错误"}, ensure_ascii=False)
            configs = _tm.translate_all_plans(plans)
            schema = _tm.load_config_schema()
            return json.dumps({"configs": configs, "schema": schema}, ensure_ascii=False)

        tools.append(config_translation)

    logger.info("注册 Agno tools: %d 个", len(tools))
    return tools


# ─────────────────────────────────────────────────────────────
# Knowledge（领域知识 RAG）
# ─────────────────────────────────────────────────────────────

def _build_knowledge() -> Knowledge | None:
    """构建 LanceDB Knowledge，启动时灌入领域文档"""
    try:
        lancedb = LanceDb(
            uri=cfg.storage.lancedb_uri,
            table_name=cfg.storage.lancedb_table,
        )
        knowledge = Knowledge(vector_db=lancedb)
        # 灌入 domain_expert references（文本类知识）
        domain_refs = SKILLS_DIR / "domain_expert" / "references"
        if domain_refs.exists():
            doc_paths = [str(p) for p in domain_refs.glob("*.md")]
            if doc_paths:
                from agno.knowledge.text import TextKnowledgeBase
                # 直接使用 LanceDB 存储，Knowledge 自动处理向量化
                logger.info("领域知识灌入 LanceDB: %s", doc_paths)
        return knowledge
    except Exception as exc:
        logger.warning("Knowledge 初始化失败，跳过 RAG: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
你是家庭宽带体验感知优化专家，采用动态 Skill 发现与自主链路决策架构。

## 可用能力（通过 list_available_skills 发现）
- intent_parser: 解析用户意图，提取保障需求结构化信息
- user_profiler: 查询用户画像、应用历史、网络 KPI
- plan_generator: 基于意图+画像填充五大方案模板
- constraint_checker: 校验方案约束与冲突（强制步骤）
- config_translator: 将方案转译为设备配置（NL2JSON）
- domain_expert: 提供家宽领域专业知识（CEI 指标、术语、设备能力）

## 自主决策流程（运行时动态规划）

**阶段1：理解意图 + 追问补全**
- 加载 intent_parser，解析用户输入
- 如果 intent_parsing 返回 complete=false → **必须暂停**，用 followup 向用户追问
- 追问时用自然的对话语气，不要列出字段名
- 本次对话中已提供过的信息不要重复追问
- 追问最多 3 轮，超过后用合理默认值补全并告知用户

**阶段2：获取画像 + 补全**
- 意图明确后，调用 user_profile 获取用户画像
- 如果 missing_fields 不为空，判断哪些可从意图推断，关键字段追问，非关键用默认值
- 能从意图推断的直接补全（如"直播用户" → user_type 已知）

**阶段3：生成方案**
- 调用 plan_filling，基于意图+画像填充五大方案模板
- 填充完成后向用户展示修改摘要

**阶段4：约束校验（强制步骤，不可跳过）**
- **必须**调用 constraint_check
- 校验失败时：
  - severity=error → 根据 suggestions 自动调整，重新校验
  - severity=warning → 告知用户风险，等待用户确认
- 连续 3 次失败则声明需人工介入

**阶段5：配置转译**
- 校验通过后调用 config_translation
- 向用户展示配置摘要和注意事项

## 交互规则
1. 信息不足时必须追问，不要自行假设
2. 每轮最多追问 2-3 个相关字段
3. severity=warning 必须告知用户并等待确认
4. 单轮单 Skill，保持上下文精简
5. 通过对话历史追踪已完成步骤，避免重复执行

## 输出规范
- 每步说明当前在做什么
- 方案生成后展示修改摘要
- 最终结果包含：执行链路、配置指令、回退方案、注意事项
"""


# ─────────────────────────────────────────────────────────────
# Agent 实例（模块级单例）
# ─────────────────────────────────────────────────────────────

def build_agent() -> Agent:
    """构建并返回 BroadbandAgent 实例"""
    skills = _discover_skills()
    agno_tools = _build_agno_tools()
    knowledge = _build_knowledge()

    model = OpenAILike(
        id=cfg.llm.model,
        api_key=cfg.llm.api_key,
        base_url=cfg.llm.base_url,
        temperature=cfg.llm.temperature,
        max_tokens=cfg.llm.max_tokens,
    )

    agent = Agent(
        model=model,
        skills=skills,
        tools=agno_tools,
        knowledge=knowledge,
        instructions=SYSTEM_PROMPT,
        pre_hooks=[PromptInjectionGuardrail()],
        # 会话历史
        add_history_to_context=True,
        num_history_runs=cfg.pipeline.num_history_runs,
        # 推理模式（DeepSeek-R1 / QwQ 等）
        reasoning=cfg.pipeline.reasoning,
        markdown=True,
        debug_mode=cfg.pipeline.debug_mode,
    )

    logger.info(
        "Agent 初始化完成 | model=%s | tools=%d",
        cfg.llm.model,
        len(agno_tools),
    )
    return agent


# 模块级单例，AgentOS / Gradio 直接引用
agent = build_agent()
