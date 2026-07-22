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

    def test_exposes_model_routes_without_forcing_a_cli_override(self) -> None:
        for target in (
            "ai-model-doctor:",
            "ai-models:",
            "ai-route:",
            "ai-provider-test:",
        ):
            self.assertIn(target, MAKEFILE_AGENT)
        self.assertIn("AGENT ?=\n", MAKEFILE_AGENT)
        self.assertIn("MODEL_PHASE ?=\n", MAKEFILE_AGENT)
        self.assertIn('$(if $(AGENT),--agent "$(AGENT)",)', MAKEFILE_AGENT)


if __name__ == "__main__":
    unittest.main()
