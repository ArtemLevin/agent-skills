from __future__ import annotations

import unittest

from agentkit.models import RunMode
from agentkit.triage import classify_task


class TriageTests(unittest.TestCase):
    def test_documentation_change_is_fast(self) -> None:
        result = classify_task("Fix typo in README documentation", RunMode.AUTO)
        self.assertEqual(result.mode, RunMode.FAST)
        self.assertNotIn("change-planner", result.selected_skills)

    def test_database_migration_is_deep(self) -> None:
        result = classify_task("Add PostgreSQL schema migration", RunMode.AUTO)
        self.assertEqual(result.mode, RunMode.DEEP)
        self.assertIn("database-review", result.selected_skills)

    def test_explicit_mode_wins(self) -> None:
        result = classify_task("Change auth schema", RunMode.STANDARD)
        self.assertEqual(result.mode, RunMode.STANDARD)


if __name__ == "__main__":
    unittest.main()
