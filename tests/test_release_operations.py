from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from agentkit.entrypoint import main
from agentkit.operations import create_diagnostics_bundle, self_test, version_payload


class ReleaseOperationTests(unittest.TestCase):
    def _project(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        with redirect_stdout(StringIO()):
            self.assertEqual(
                main(["--project-root", str(root), "init", "--skip-graphify-install"]),
                0,
            )

    def test_self_test_and_verbose_version(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agentkit release path ") as directory:
            root = Path(directory)
            self._project(root)
            result = self_test(root)
            self.assertTrue(result["ready"], result)
            version = version_payload(root)
            self.assertEqual(version["agentkit_version"], "1.0.4")
            self.assertEqual(version["installed_project_version"], "1.0.4")

    def test_diagnostics_bundle_is_bounded_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            config = root / ".agent/agentkit.toml"
            config.write_text(
                config.read_text(encoding="utf-8")
                + '\nsecret = "ordinary-literal-secret"\n',
                encoding="utf-8",
            )
            result = create_diagnostics_bundle(root)
            bundle = Path(result["path"])
            self.assertTrue(bundle.is_file())
            with zipfile.ZipFile(bundle) as archive:
                names = archive.namelist()
                self.assertIn("manifest.json", names)
                self.assertNotIn("implementation.stdout.txt", names)
                combined = b"\n".join(archive.read(name) for name in names)
            self.assertNotIn(b"ordinary-literal-secret", combined)
            self.assertIn(b"[REDACTED]", combined)
            manifest = json.loads(zipfile.ZipFile(bundle).read("manifest.json"))
            self.assertTrue(manifest["redacted"])

    def test_diagnostics_survives_corrupt_installation_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            (root / ".agent/installation.json").write_text(
                '{"secret": "ordinary-literal-secret"', encoding="utf-8"
            )
            version = version_payload(root)
            self.assertEqual(version["installed_project_version"], "invalid")
            result = create_diagnostics_bundle(root)
            with zipfile.ZipFile(result["path"]) as archive:
                self.assertIn(
                    "installation.invalid.redacted.txt", archive.namelist()
                )
                combined = b"\n".join(
                    archive.read(name) for name in archive.namelist()
                )
            self.assertNotIn(b"ordinary-literal-secret", combined)


if __name__ == "__main__":
    unittest.main()
