"""Skills 发现与注册模块 — 自动扫描 skills/ 目录，读取 SKILL.md frontmatter"""
import re
from pathlib import Path
from typing import Any

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def _parse_frontmatter(skill_md: str) -> dict[str, str]:
    """解析 SKILL.md 中的 YAML frontmatter（name + description）"""
    match = re.match(r"^---\s*\n(.*?)\n---", skill_md, re.DOTALL)
    if not match:
        return {}
    fm_text = match.group(1)
    result: dict[str, str] = {}
    # 解析 name
    name_match = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
    if name_match:
        result["name"] = name_match.group(1).strip()
    # 解析 description（支持多行 >- 格式）
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
