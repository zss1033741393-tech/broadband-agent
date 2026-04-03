"""Skills 发现与注册模块

职责：
  1. discover_skills()     — 扫描 skills/ 目录，读取 SKILL.md frontmatter
  2. build_skills_summary() — 为 system prompt 构建 Skill 摘要文本
  3. build_agno_tools()    — 将有 scripts/ 的 Skill 注册为 Agno Function tools
                             供 agno.agent.Agent 的 LLM 通过 tool_call 真实调用
"""
from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from agno.tools import tool
from agno.tools.function import Function

logger = logging.getLogger("skill_loader")

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


# ─────────────────────────────────────────────────────────────
# Skill 元数据发现
# ─────────────────────────────────────────────────────────────

def _parse_frontmatter(skill_md: str) -> dict[str, str]:
    """解析 SKILL.md 中的 YAML frontmatter（name + description）"""
    match = re.match(r"^---\s*\n(.*?)\n---", skill_md, re.DOTALL)
    if not match:
        return {}
    fm_text = match.group(1)
    result: dict[str, str] = {}

    name_match = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
    if name_match:
        result["name"] = name_match.group(1).strip()

    # 支持多行 > 格式的 description
    desc_match = re.search(r"description:\s*>\n((?:  .+\n?)+)", fm_text)
    if desc_match:
        lines = desc_match.group(1).splitlines()
        result["description"] = " ".join(line.strip() for line in lines if line.strip())
    else:
        desc_inline = re.search(r"^description:\s*(.+)$", fm_text, re.MULTILINE)
        if desc_inline:
            result["description"] = desc_inline.group(1).strip()

    return result


def discover_skills() -> list[dict[str, Any]]:
    """扫描 skills/ 目录，返回所有 Skill 的元数据列表"""
    skills: list[dict[str, Any]] = []
    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            continue

        content = skill_md_path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        if not fm.get("name"):
            continue

        scripts_dir = skill_dir / "scripts"
        references_dir = skill_dir / "references"
        skills.append({
            "name": fm["name"],
            "description": fm.get("description", ""),
            "skill_dir": str(skill_dir),
            "skill_md": content,
            "has_scripts": scripts_dir.exists(),
            "has_references": references_dir.exists(),
        })

    return skills


def build_skills_summary(skills: list[dict[str, Any]]) -> str:
    """将 Skills 列表构建为 system prompt 中的摘要文本"""
    lines: list[str] = []
    for skill in skills:
        lines.append(f"- **{skill['name']}**: {skill['description']}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Agno Tool 注册
# ─────────────────────────────────────────────────────────────

def build_agno_tools(skills: list[dict[str, Any]]) -> list[Function]:
    """将每个 Skill 注册为 Agno Function tool。

    有 scripts/ 的 Skill：动态加载脚本模块，调用其核心入口函数，返回结构化结果。
    无 scripts/ 的 Skill（如 domain_knowledge）：返回 references/ 中的参考资料。

    LLM 通过标准 tool_call 机制调用这些函数，不再靠文本解析"推断" Skill 使用。
    """
    agno_tools: list[Function] = []
    for skill in skills:
        fn = _build_tool_for_skill(skill)
        if fn is not None:
            agno_tools.append(fn)
            logger.debug("注册 Agno tool | skill=%s", skill["name"])
    return agno_tools


def _load_references(skill_dir: Path) -> dict[str, str]:
    """读取 references/ 目录下所有文件内容"""
    refs: dict[str, str] = {}
    ref_dir = skill_dir / "references"
    if not ref_dir.exists():
        return refs
    for f in sorted(ref_dir.iterdir()):
        if f.is_file():
            refs[f.name] = f.read_text(encoding="utf-8")
    return refs


def _import_script_module(skill_dir: Path, module_filename: str) -> Any | None:
    """动态导入 scripts/{module_filename}，返回模块对象；失败时返回 None"""
    module_path = skill_dir / "scripts" / module_filename
    if not module_path.exists():
        return None
    module_name = f"_skill_{skill_dir.name}_{module_filename[:-3]}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _build_tool_for_skill(skill: dict[str, Any]) -> Function | None:
    """为单个 Skill 构建 Agno Function tool"""
    name: str = skill["name"]
    description: str = skill["description"]
    skill_dir = Path(skill["skill_dir"])

    # 各 Skill 对应各自的核心脚本和入口函数
    _SKILL_DISPATCH: dict[str, tuple[str, str]] = {
        "intent_parsing":    ("parse_intent.py",    "_tool_intent_parsing"),
        "user_profile":      ("profile_handler.py", "_tool_user_profile"),
        "plan_filling":      ("filler.py",           "_tool_plan_filling"),
        "constraint_check":  ("checker.py",          "_tool_constraint_check"),
        "config_translation":("translator.py",       "_tool_config_translation"),
    }

    if name in _SKILL_DISPATCH:
        script_file, builder_name = _SKILL_DISPATCH[name]
        mod = _import_script_module(skill_dir, script_file)
        if mod is None:
            logger.warning("Skill %s 脚本加载失败，跳过 tool 注册", name)
            return None
        builder = globals().get(builder_name)
        if builder is None:
            logger.warning("tool builder %s 未定义", builder_name)
            return None
        return builder(mod, skill_dir, description)

    # domain_knowledge 或未知 Skill：返回 references 内容
    return _tool_references_only(name, description, skill_dir)


# ─────────────────────────────────────────────────────────────
# 各 Skill 的 Agno tool builder
# ─────────────────────────────────────────────────────────────

def _tool_intent_parsing(mod: Any, skill_dir: Path, description: str) -> Function:
    """intent_parsing — 校验意图完整性，生成追问或返回完整意图"""

    @tool(name="intent_parsing", description=description)
    def intent_parsing(intent_goal_json: str) -> str:
        """
        校验用户意图目标的完整性。

        Args:
            intent_goal_json: 当前已提取到的意图字段，JSON 字符串格式。
                              如果是首次解析，传入空 JSON 对象 "{}"。
        Returns:
            JSON 字符串，包含：
              complete (bool)       — 意图是否完整
              missing_fields (list) — 缺失的字段列表
              followup (str)        — 建议的追问话术（complete=false 时有值）
              schema (dict)         — 意图目标的完整字段定义
        """
        try:
            intent_goal = json.loads(intent_goal_json) if intent_goal_json.strip() else {}
        except json.JSONDecodeError:
            intent_goal = {}

        complete, missing = mod.validate_intent(intent_goal)
        followup = mod.generate_followup_questions(missing) if not complete else ""
        schema = mod.load_intent_schema()

        return json.dumps(
            {
                "complete": complete,
                "missing_fields": missing,
                "followup": followup,
                "schema": schema,
            },
            ensure_ascii=False,
        )

    return intent_parsing  # type: ignore[return-value]


def _tool_user_profile(mod: Any, skill_dir: Path, description: str) -> Function:
    """user_profile — 返回用户画像模板和字段规则"""

    @tool(name="user_profile", description=description)
    def user_profile(known_info_json: str = "{}") -> str:
        """
        获取用户画像模板，并标注哪些字段仍缺失。

        Args:
            known_info_json: 已知的用户信息，JSON 字符串。
        Returns:
            JSON 字符串，包含：
              template (dict)       — 画像字段模板
              missing_fields (list) — 仍需补全的字段
              field_rules (str)     — 字段补全规则说明
        """
        try:
            known = json.loads(known_info_json) if known_info_json.strip() else {}
        except json.JSONDecodeError:
            known = {}

        profile = mod.get_empty_profile()
        # 将已知信息合并进画像
        profile["user_profile"].update(known)

        missing = mod.check_missing_fields(profile)
        rules = mod.load_field_rules()

        return json.dumps(
            {
                "template": profile,
                "missing_fields": missing,
                "field_rules": rules,
            },
            ensure_ascii=False,
        )

    return user_profile  # type: ignore[return-value]


def _tool_plan_filling(mod: Any, skill_dir: Path, description: str) -> Function:
    """plan_filling — 并行填充五大方案模板"""

    @tool(name="plan_filling", description=description)
    async def plan_filling(intent_goal_json: str) -> str:
        """
        基于意图目标并行填充五大方案模板。

        Args:
            intent_goal_json: 完整的意图目标，JSON 字符串。
        Returns:
            JSON 字符串，包含：
              plans (dict)    — 各方案名称 → 填充后的模板内容
              changes (dict)  — 各方案中被修改的字段说明
              rules (str)     — 本次参数决策依据的规则摘要
        """
        try:
            intent_goal = json.loads(intent_goal_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "intent_goal_json 格式错误"}, ensure_ascii=False)

        params = mod.build_params_from_intent(intent_goal)
        filled_plans, all_changes = await mod.fill_all_templates(params)
        rules = mod.load_filling_rules()

        return json.dumps(
            {
                "plans": filled_plans,
                "changes": all_changes,
                "rules": rules[:500],  # 规则文本较长，截取摘要
            },
            ensure_ascii=False,
        )

    return plan_filling  # type: ignore[return-value]


def _tool_constraint_check(mod: Any, skill_dir: Path, description: str) -> Function:
    """constraint_check — 执行性能 + 冲突约束校验"""

    @tool(name="constraint_check", description=description)
    def constraint_check(plans_json: str, guarantee_period_json: str = "{}") -> str:
        """
        对填充后的方案执行约束校验。

        Args:
            plans_json:            fill_plans 返回的 plans 字段，JSON 字符串。
            guarantee_period_json: 保障时段 {start_time, end_time}，JSON 字符串。
        Returns:
            JSON 字符串，包含：
              passed (bool)        — 是否全部通过
              violations (list)    — 违反的约束列表，每项含 type/message/field
        """
        try:
            plans = json.loads(plans_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "plans_json 格式错误"}, ensure_ascii=False)

        try:
            guarantee_period = json.loads(guarantee_period_json)
        except json.JSONDecodeError:
            guarantee_period = {}

        violations = mod.run_all_checks(plans, guarantee_period)
        return json.dumps(
            {
                "passed": len(violations) == 0,
                "violations": violations,
            },
            ensure_ascii=False,
        )

    return constraint_check  # type: ignore[return-value]


def _tool_config_translation(mod: Any, skill_dir: Path, description: str) -> Function:
    """config_translation — 将方案 JSON 转译为设备配置"""

    @tool(name="config_translation", description=description)
    def config_translation(plans_json: str) -> str:
        """
        将语义化方案 JSON 转译为设备可下发的配置格式（NL2JSON）。

        Args:
            plans_json: fill_plans 返回的 plans 字段，JSON 字符串。
        Returns:
            JSON 字符串，包含：
              configs (dict)   — 各配置类型 → 设备配置 JSON
              schema (dict)    — 设备配置 JSON Schema（用于格式校验）
        """
        try:
            plans = json.loads(plans_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "plans_json 格式错误"}, ensure_ascii=False)

        configs = mod.translate_all_plans(plans)
        schema = mod.load_config_schema()

        return json.dumps(
            {"configs": configs, "schema": schema},
            ensure_ascii=False,
        )

    return config_translation  # type: ignore[return-value]


def _tool_references_only(name: str, description: str, skill_dir: Path) -> Function:
    """无脚本的 Skill（如 domain_knowledge）：直接返回 references/ 内容"""
    refs = _load_references(skill_dir)

    @tool(name=name, description=description)
    def references_skill(query: str = "") -> str:
        """
        返回该 Skill 的参考资料内容。

        Args:
            query: 可选，查询关键词，用于过滤返回哪些参考文件。
        Returns:
            JSON 字符串，包含各参考文件的内容。
        """
        if query:
            filtered = {k: v for k, v in refs.items() if query.lower() in k.lower() or query in v}
            return json.dumps(filtered or refs, ensure_ascii=False)
        return json.dumps(refs, ensure_ascii=False)

    return references_skill  # type: ignore[return-value]
