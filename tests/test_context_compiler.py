from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentkit.config import ContextConfig
from agentkit.context_compiler import ContextCompiler


class ContextCompilerTests(unittest.TestCase):
    def test_canonicalizes_project_root_before_relativizing_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            target = root / "worker.py"
            target.write_text("def work():\n    return True\n", encoding="utf-8")
            compiler = ContextCompiler(
                root / "nested" / "..",
                ContextConfig(cache_enabled=False),
            )

            self.assertEqual(compiler.project_root, root.resolve())
            self.assertEqual(compiler._candidate_files("worker"), [target])

    def test_compiles_bounded_context_and_hits_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / ".agent" / "skills" / "implementation").mkdir(
                parents=True
            )
            (root / "src" / "payment_service.py").write_text(
                "class PaymentService:\n    pass\n\n"
                "def retry_payment():\n    return True\n",
                encoding="utf-8",
            )
            (root / "tests" / "test_payment_service.py").write_text(
                "def test_retry():\n    assert True\n",
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                '[project]\nname="demo"\ndependencies=["pytest"]\n'
                "[tool.pytest.ini_options]\n",
                encoding="utf-8",
            )
            (
                root
                / ".agent"
                / "skills"
                / "implementation"
                / "SKILL.md"
            ).write_text(
                "---\nname: implementation\ndescription: >\n"
                "  Apply the smallest code change.\n---\n",
                encoding="utf-8",
            )
            config = ContextConfig(
                cache_path=".agent/cache/context.db",
                profile_path=".agent/project-profile.json",
                max_context_chars=4000,
            )
            compiler = ContextCompiler(root, config)
            first = compiler.compile(
                task="Fix retry in payment service",
                phase="implementation",
                selected_skills=["implementation"],
            )
            second = compiler.compile(
                task="Fix retry in payment service",
                phase="implementation",
                selected_skills=["implementation"],
            )
            self.assertFalse(first.cache_hit)
            self.assertTrue(second.cache_hit)
            self.assertIn("src/payment_service.py", first.candidate_files)
            self.assertIn("class PaymentService", first.content)
            self.assertLessEqual(len(first.content), 4000)
            output = compiler.write(first)
            self.assertTrue(output.is_file())

    def test_selected_file_change_invalidates_cached_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            target = root / "src" / "worker.py"
            target.write_text(
                "def process():\n    return 1\n",
                encoding="utf-8",
            )
            config = ContextConfig(
                cache_path=".agent/cache/context.db",
                profile_path=".agent/project-profile.json",
            )
            compiler = ContextCompiler(root, config)
            first = compiler.compile(
                task="Change worker process",
                phase="plan",
            )
            target.write_text(
                "def process():\n    return 2\n",
                encoding="utf-8",
            )
            second = compiler.compile(
                task="Change worker process",
                phase="plan",
            )
            self.assertFalse(first.cache_hit)
            self.assertFalse(second.cache_hit)
            self.assertNotEqual(first.fingerprint, second.fingerprint)


if __name__ == "__main__":
    unittest.main()
