from __future__ import annotations

import unittest

from agentkit.review import parse_review


class ReviewTests(unittest.TestCase):
    def test_parses_json_fence(self) -> None:
        report = parse_review(
            'progress\n```json\n{"verdict":"changes_required","findings":'
            '[{"severity":"P1","issue":"race"}]}\n```'
        )
        self.assertEqual(report.verdict, "changes_required")
        self.assertEqual(len(report.blocking_findings), 1)

    def test_unstructured_review_fails_closed(self) -> None:
        report = parse_review("Looks good to me")
        self.assertEqual(report.verdict, "unstructured")
        self.assertEqual(report.blocking_findings[0].severity, "P1")


if __name__ == "__main__":
    unittest.main()
