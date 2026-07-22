from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentkit.config import ContextConfig, SecurityConfig
from agentkit.quality.ci_config import QualityCIConfig
from agentkit.quality.ci_runner import (
    QualityCIRunner,
    RepositoryComparison,
)
from agentkit.quality.config import QualityConfig
from agentkit.quality.gate_models import (
    QualityDiff,
    QualityGateResult,
    QualityGateViolation,
    QualityMetricDelta,
)


class _FakeLifecycle:
    def capture_baseline(self, run_directory: Path):
        before = run_directory / "quality-before.json"
        hotspots = run_directory / "quality-hotspots.json"
        provider = run_directory / "quality-provider.json"
        before.write_text('{"availability":"available"}', encoding="utf-8")
        hotspots.write_text('{"hotspots":[]}', encoding="utf-8")
        provider.write_text('{"provider":"fake"}', encoding="utf-8")
        result = SimpleNamespace(
            artifacts=SimpleNamespace(
                snapshot_path=before,
                hotspots_path=hotspots,
                provider_path=provider,
            )
        )
        return SimpleNamespace(
            strategy="merge_base",
            result=result,
            merge_base="base",
            worktree_path="",
            warnings=(),
        )

    def finalize(self, run_directory: Path, baseline):
        after = run_directory / "quality-after.json"
        after_hotspots = run_directory / "quality-after-hotspots.json"
        provider_after = run_directory / "quality-provider-after.json"
        after.write_text('{"availability":"available"}', encoding="utf-8")
        after_hotspots.write_text('{"hotspots":[]}', encoding="utf-8")
        provider_after.write_text('{"provider":"fake"}', encoding="utf-8")
        diff = QualityDiff(
            provider="fake",
            provider_version="1",
            baseline_fingerprint="a",
            current_fingerprint="b",
            comparable=True,
            metrics={
                "score": QualityMetricDelta("score", 1, 9, 8, True),
            },
        )
        gate = QualityGateResult(
            mode="enforce",
            unavailable_policy="warn",
            available=True,
            comparable=True,
            passed=False,
            allowed=False,
            violations=(
                QualityGateViolation(
                    kind="delta",
                    metric="score",
                    threshold=5,
                    baseline=1,
                    current=9,
                    delta=8,
                    message="score regression",
                ),
            ),
        )
        diff_path = run_directory / "quality-diff.json"
        gate_path = run_directory / "quality-gate.json"
        diff_path.write_text(json.dumps(diff.to_dict()), encoding="utf-8")
        gate_path.write_text(json.dumps(gate.to_dict()), encoding="utf-8")
        current = SimpleNamespace(
            artifacts=SimpleNamespace(
                snapshot_path=after,
                hotspots_path=after_hotspots,
                provider_path=provider_after,
            )
        )
        return SimpleNamespace(
            baseline=baseline,
            current=current,
            diff=diff,
            gate=gate,
            diff_path=diff_path,
            gate_path=gate_path,
        )


class QualityCIRunnerTests(unittest.TestCase):
    def _runner(self, root: Path) -> QualityCIRunner:
        core = SimpleNamespace(
            context=ContextConfig(cache_enabled=False),
            security=SecurityConfig(
                allowed_executables=["git", "strictacode"],
                denied_substrings=[],
            ),
        )
        return QualityCIRunner(
            root,
            core,
            QualityConfig(mode="enforce"),
            QualityCIConfig(),
        )

    def test_shallow_clone_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = self._runner(Path(directory))
            with patch.object(
                runner,
                "_git_text",
                side_effect=["true", "true"],
            ):
                with self.assertRaisesRegex(RuntimeError, "fetch-depth: 0"):
                    runner.inspect_repository("origin/main")

    def test_clean_head_cannot_be_its_own_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = self._runner(Path(directory))
            with patch.object(
                runner,
                "_git_text",
                side_effect=["true", "false", "abc", "abc", "abc", ""],
            ):
                with self.assertRaisesRegex(RuntimeError, "current clean HEAD"):
                    runner.inspect_repository("main")

    def test_run_packages_artifacts_and_preserves_gate_exit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent kit ") as directory:
            root = Path(directory)
            runner = self._runner(root)
            repository = RepositoryComparison(
                base_ref="origin/main",
                head="head",
                base_commit="base",
                merge_base="base",
                dirty=False,
            )
            with (
                patch.object(
                    runner,
                    "inspect_repository",
                    return_value=repository,
                ),
                patch(
                    "agentkit.quality.ci_runner.QualityLifecycle",
                    return_value=_FakeLifecycle(),
                ),
            ):
                result = runner.run(
                    base_ref="origin/main",
                    run_id="ci-test",
                )
            self.assertEqual(result.exit_code, 6)
            artifacts = root / ".agent/state/runs/ci-test/ci-artifacts"
            for name in (
                "quality-baseline.json",
                "quality-current.json",
                "quality-diff.json",
                "quality-gate.json",
                "quality-summary.md",
                "ci-result.json",
            ):
                self.assertTrue((artifacts / name).is_file(), name)
            self.assertEqual(
                (root / ".agent/state/runs/ci-test/ci-exit-code")
                .read_text(encoding="utf-8")
                .strip(),
                "6",
            )


if __name__ == "__main__":
    unittest.main()
