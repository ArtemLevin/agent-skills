from __future__ import annotations

import unittest

from agentkit import __version__
from agentkit.contracts import ARTIFACT_SCHEMAS, CORE_COMMANDS, PublicContracts
from agentkit.exit_codes import ExitCode
from agentkit.init_project import MAKEFILE_AGENT


class ReleaseContractTests(unittest.TestCase):
    def test_public_surface_is_versioned_and_stable(self) -> None:
        contracts = PublicContracts().to_dict()
        self.assertEqual(__version__, "1.0.0")
        self.assertEqual(contracts["package_version"], "1.0.0")
        self.assertEqual(sorted(contracts["exit_codes"]), list(range(7)))
        for command in ("migrate", "self-test", "diagnostics", "version"):
            self.assertIn(command, CORE_COMMANDS)
        for name in (
            "installation-manifest.schema.json",
            "migration-report.schema.json",
            "run-state.schema.json",
            "self-test.schema.json",
            "diagnostics-manifest.schema.json",
        ):
            self.assertIn(name, ARTIFACT_SCHEMAS)

    def test_release_make_targets_have_cli_parity(self) -> None:
        for target in (
            "ai-upgrade-check:",
            "ai-migrate:",
            "ai-self-test:",
            "ai-diagnostics:",
            "ai-release-check:",
        ):
            self.assertIn(target, MAKEFILE_AGENT)
        self.assertEqual(ExitCode.QUALITY_GATE_FAILED, 6)


if __name__ == "__main__":
    unittest.main()
