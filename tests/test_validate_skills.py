from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.validate_skills import parse_frontmatter, validate_repository, validate_skill


VALID_SKILL = """---
name: example-skill
description: >
  Use when a sufficiently concrete example is needed to validate routing metadata.
---

# Purpose

Purpose.

# Inputs

Inputs.

# Workflow

1. Work.

# Decision rules

- Decide.

# Output

Output.

# Stop conditions

Stop.
"""


class ParseFrontmatterTests(unittest.TestCase):
    def test_parses_folded_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example-skill" / "SKILL.md"
            path.parent.mkdir()
            path.write_text(VALID_SKILL, encoding="utf-8")

            skill = parse_frontmatter(path)

        self.assertEqual(skill.name, "example-skill")
        self.assertIn("validate routing metadata", skill.description)
        self.assertEqual(validate_skill(skill), [])

    def test_detects_directory_name_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong-directory" / "SKILL.md"
            path.parent.mkdir()
            path.write_text(VALID_SKILL, encoding="utf-8")

            errors = validate_skill(parse_frontmatter(path))

        self.assertTrue(any("must match directory" in error for error in errors))


class RepositoryValidationTests(unittest.TestCase):
    def test_valid_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_path = root / "skills" / "example-skill" / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text(VALID_SKILL, encoding="utf-8")

            errors = validate_repository(root)

        self.assertEqual(errors, [])

    def test_reports_orphan_skill_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_path = root / "skills" / "example-skill" / "SKILL.md"
            valid_path.parent.mkdir(parents=True)
            valid_path.write_text(VALID_SKILL, encoding="utf-8")
            (root / "skills" / "orphan").mkdir()

            errors = validate_repository(root)

        self.assertTrue(any("missing SKILL.md" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
