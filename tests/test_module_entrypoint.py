from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ModuleEntrypointTests(unittest.TestCase):
    def test_python_m_agentkit_uses_complete_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentkit",
                    "--project-root",
                    str(root),
                    "init",
                    "--skip-graphify-install",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / ".agent/installation.json").is_file())
            self.assertTrue((root / ".agent/schemas/run-state.schema.json").is_file())


if __name__ == "__main__":
    unittest.main()
