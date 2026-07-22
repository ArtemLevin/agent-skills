from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from agentkit.entrypoint import main
from agentkit.installation import (
    SUPPORTED_UPGRADE_VERSIONS,
    apply_migration,
    detect_legacy_version,
    installation_manifest,
    migration_report,
)


def _init(root: Path) -> None:
    with redirect_stdout(StringIO()):
        result = main(["--project-root", str(root), "init", "--skip-graphify-install"])
    if result != 0:
        raise AssertionError(f"init failed with {result}")


class InstallationMigrationTests(unittest.TestCase):
    def test_init_records_manifest_and_preserves_custom_agent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _init(root)
            manifest = installation_manifest(root)
            self.assertEqual(manifest["agentkit_version"], "1.0.2")
            agent = root / ".agent/AGENT.md"
            agent.write_text("custom project contract\n", encoding="utf-8")
            _init(root)
            self.assertEqual(agent.read_text(encoding="utf-8"), "custom project contract\n")

    def test_customized_managed_file_is_preserved_with_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _init(root)
            skill = root / ".agent/skills/task-triage/SKILL.md"
            skill.write_text("custom skill\n", encoding="utf-8")
            report = migration_report(root)
            action = next(
                item
                for item in report["actions"]
                if item["path"] == "skills/task-triage/SKILL.md"
            )
            self.assertEqual(action["action"], "preserve")
            apply_migration(root)
            self.assertEqual(skill.read_text(encoding="utf-8"), "custom skill\n")
            candidate = root / ".agent/update-candidates/skills/task-triage/SKILL.md"
            self.assertTrue(candidate.is_file())
            apply_migration(root)
            self.assertEqual(skill.read_text(encoding="utf-8"), "custom skill\n")

    def test_unchanged_managed_file_updates_with_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _init(root)
            target = root / ".agent/schemas/triage.schema.json"
            original = target.read_bytes()
            desired = b'{"version": 1, "new": true}\n'
            with patch(
                "agentkit.installation._source_resources",
                return_value={"schemas/triage.schema.json": desired},
            ):
                result = apply_migration(root)
            self.assertEqual(target.read_bytes(), desired)
            self.assertIn("schemas/triage.schema.json", result["applied"])
            backups = list((root / ".agent/backups").rglob("triage.schema.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)

    def test_report_is_json_serializable_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _init(root)
            first = apply_migration(root)
            second = apply_migration(root)
            json.dumps(first)
            self.assertEqual(second["applied"], [])

    def test_detects_every_supported_legacy_release_by_capability_marker(self) -> None:
        markers = {
            "0.4.0": "compiled-context.schema.json",
            "0.5.0": "quality-snapshot.schema.json",
            "0.6.0": "quality-gate.schema.json",
            "0.7.0": "hotspot-context.schema.json",
            "0.8.0": "verification-plan.schema.json",
            "0.9.0": "quality-ci-result.schema.json",
            "0.10.0": "eval-run.schema.json",
            "0.11.0": "model-route.schema.json",
        }
        self.assertEqual(tuple(markers), SUPPORTED_UPGRADE_VERSIONS)
        for version, marker in markers.items():
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                schema = root / ".agent/schemas" / marker
                schema.parent.mkdir(parents=True)
                schema.write_text("{}", encoding="utf-8")
                self.assertEqual(detect_legacy_version(root), version)

    def test_pre_04_installation_is_blocked_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".agent").mkdir()
            result = apply_migration(root)
            self.assertFalse(result["compatible"])
            self.assertTrue(result["blocking_conflicts"])
            self.assertFalse((root / ".agent/installation.json").exists())

    def test_04_upgrade_preserves_configuration_and_custom_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema = root / ".agent/schemas/compiled-context.schema.json"
            schema.parent.mkdir(parents=True)
            schema.write_text("{}\n", encoding="utf-8")
            config = root / ".agent/agentkit.toml"
            config.write_text(
                'version = 1\n\n[agent]\nplatform = "custom"\n'
                '\n[organization]\npolicy = "preserve-me"\n',
                encoding="utf-8",
            )
            contract = root / ".agent/AGENT.md"
            contract.write_text("custom 0.4 contract\n", encoding="utf-8")
            self.assertEqual(detect_legacy_version(root), "0.4.0")
            result = apply_migration(root)
            self.assertTrue(result["compatible"])
            self.assertIn('platform = "custom"', config.read_text(encoding="utf-8"))
            self.assertIn("preserve-me", config.read_text(encoding="utf-8"))
            self.assertEqual(contract.read_text(encoding="utf-8"), "custom 0.4 contract\n")
            self.assertEqual(installation_manifest(root)["previous_version"], "0.4.0")
            makefile = (root / ".agent/Makefile.agent").read_text(encoding="utf-8")
            self.assertEqual(makefile.count("# BEGIN AGENTKIT RELEASE"), 1)
            self.assertIn("ai-release-check:", makefile)


if __name__ == "__main__":
    unittest.main()
