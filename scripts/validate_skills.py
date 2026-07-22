#!/usr/bin/env python3
"""Validate the structure and activation metadata of repository skills."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_SECTIONS = (
    "# Purpose",
    "# Inputs",
    "# Workflow",
    "# Decision rules",
    "# Output",
    "# Stop conditions",
)
MAX_SKILL_LINES = 500


@dataclass(frozen=True)
class Skill:
    directory: str
    name: str
    description: str
    content: str
    path: Path


def parse_frontmatter(path: Path) -> Skill:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening YAML frontmatter delimiter")

    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("missing closing YAML frontmatter delimiter") from exc

    fields: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in lines[1:end]:
        if raw_line.startswith((" ", "\t")) and current_key:
            fields[current_key] = f"{fields[current_key]} {raw_line.strip()}".strip()
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        fields[current_key] = "" if value in {">", "|"} else value.strip("\"'")

    return Skill(
        directory=path.parent.name,
        name=fields.get("name", ""),
        description=fields.get("description", "").strip(),
        content=content,
        path=path,
    )


def validate_skill(skill: Skill) -> list[str]:
    errors: list[str] = []
    label = skill.path.relative_to(ROOT)

    if not skill.name:
        errors.append(f"{label}: missing frontmatter field 'name'")
    elif not NAME_RE.fullmatch(skill.name):
        errors.append(f"{label}: name must use kebab-case")

    if skill.name != skill.directory:
        errors.append(f"{label}: name '{skill.name}' must match directory '{skill.directory}'")

    if len(skill.description) < 60:
        errors.append(f"{label}: description is too short to route reliably")
    if "use" not in skill.description.lower():
        errors.append(f"{label}: description should state when to use the skill")

    for section in REQUIRED_SECTIONS:
        if section not in skill.content:
            errors.append(f"{label}: missing required section {section!r}")

    line_count = len(skill.content.splitlines())
    if line_count > MAX_SKILL_LINES:
        errors.append(f"{label}: {line_count} lines exceeds {MAX_SKILL_LINES}; move detail to references/")

    return errors


def validate_repository(root: Path = ROOT) -> list[str]:
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return ["skills/: directory does not exist"]

    errors: list[str] = []
    names: dict[str, Path] = {}
    paths = sorted(skills_dir.glob("*/SKILL.md"))
    if not paths:
        return ["skills/: no SKILL.md files found"]

    for path in paths:
        try:
            skill = parse_frontmatter(path)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
            continue

        errors.extend(validate_skill(skill))
        if skill.name in names:
            errors.append(
                f"{path.relative_to(root)}: duplicate skill name also used by "
                f"{names[skill.name].relative_to(root)}"
            )
        elif skill.name:
            names[skill.name] = path

    orphan_dirs = sorted(
        path.relative_to(root) for path in skills_dir.iterdir() if path.is_dir() and not (path / "SKILL.md").is_file()
    )
    errors.extend(f"{path}: missing SKILL.md" for path in orphan_dirs)
    return errors


def main() -> int:
    errors = validate_repository()
    if errors:
        print("Skill validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    count = len(list(SKILLS_DIR.glob("*/SKILL.md")))
    print(f"Validated {count} skills successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
