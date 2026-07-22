from __future__ import annotations

import unittest

from agentkit.init_project import MAKEFILE_AGENT


class ContextMakefileTests(unittest.TestCase):
    def test_exposes_every_context_and_cache_operation(self) -> None:
        for target in (
            "ai-context:",
            "ai-profile:",
            "ai-profile-refresh:",
            "ai-cache-stats:",
            "ai-cache-list:",
            "ai-cache-prune:",
            "ai-cache-clear:",
            "ai-context-maintain:",
        ):
            self.assertIn(target, MAKEFILE_AGENT)


if __name__ == "__main__":
    unittest.main()
