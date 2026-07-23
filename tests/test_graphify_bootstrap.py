from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from agentkit.commands import CommandPolicy
from agentkit.config import GraphifyConfig, write_default_config
from agentkit.doctor import doctor
from agentkit.entrypoint import main as entrypoint_main
from agentkit.executables import ExecutableResolution, resolve_executable
from agentkit.graphify import (
    GraphifyClient,
    ensure_graphify_ignore,
    graphify_output_graph_path,
    graphify_rebuild_marker,
    install_graphify_project_skill,
    root_graph_path,
)
from agentkit.models import CommandResult


class ExecutableResolverTests(unittest.TestCase):
    def test_path_lookup_has_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "graphify"
            executable.write_text("", encoding="utf-8")
            result = resolve_executable(
                "graphify",
                path_lookup=lambda _: str(executable),
                candidate_directories=[],
            )
        self.assertTrue(result.found)
        self.assertEqual(result.source, "path")
        self.assertEqual(result.path, executable.resolve())

    def test_resolves_executable_from_tool_environment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="Агент Kit path with spaces ") as directory:
            scripts = Path(directory)
            executable = scripts / "graphify.exe"
            executable.write_text("launcher", encoding="utf-8")
            result = resolve_executable(
                "graphify",
                path_lookup=lambda _: None,
                candidate_directories=[scripts],
            )
        self.assertTrue(result.found)
        self.assertEqual(result.source, "agentkit_tool_environment")
        self.assertEqual(result.path, executable.resolve())


class GraphifyBootstrapTests(unittest.TestCase):
    def _resolution(self, executable: Path) -> ExecutableResolution:
        return ExecutableResolution(
            name="graphify",
            path=executable,
            source="agentkit_tool_environment",
            package="graphifyy",
            package_version="0.9.23",
        )

    def _result(self, *, returncode: int = 0) -> CommandResult:
        return CommandResult(
            command=[],
            returncode=returncode,
            stdout="ok" if returncode == 0 else "",
            stderr="" if returncode == 0 else "failed",
            duration_seconds=0.1,
        )

    def _write_output_graph(self, root: Path, content: str = '{"nodes": []}\n') -> Path:
        graph = graphify_output_graph_path(root)
        graph.parent.mkdir(parents=True, exist_ok=True)
        graph.write_text(content, encoding="utf-8")
        return graph

    def _client(self, root: Path) -> GraphifyClient:
        executable = root / "tool env" / "graphify.exe"
        return GraphifyClient(
            root,
            GraphifyConfig(),
            CommandPolicy(["graphify"], []),
            resolution=self._resolution(executable),
        )

    def test_project_install_uses_absolute_resolved_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "tool env" / "graphify.exe"
            expected = CompletedProcess([], 0, stdout="installed", stderr="")
            with patch("agentkit.graphify.subprocess.run", return_value=expected) as run:
                payload = install_graphify_project_skill(
                    root,
                    platform="agents",
                    required=True,
                    resolution=self._resolution(executable),
                )
        command = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertEqual(command[0], str(executable))
        self.assertEqual(command[1:], ["install", "--project", "--platform", "agents"])
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")
        self.assertEqual(kwargs["env"]["PYTHONUTF8"], "1")
        self.assertEqual(kwargs["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertTrue(payload["installed"])

    def test_missing_executable_is_nonfatal_for_init_but_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = install_graphify_project_skill(
                root,
                required=False,
                resolution=ExecutableResolution(
                    name="graphify",
                    path=None,
                    source="unavailable",
                    package="graphifyy",
                    package_version="0.9.23",
                ),
            )
        self.assertFalse(payload["attempted"])
        self.assertIn("agentkit graph install", payload["repair_command"])

    def test_explicit_repair_fails_when_executable_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "could not be resolved"):
                install_graphify_project_skill(
                    root,
                    required=True,
                    resolution=ExecutableResolution(
                        name="graphify",
                        path=None,
                        source="unavailable",
                        package="graphifyy",
                        package_version="0.9.23",
                    ),
                )

    def test_graph_client_uses_absolute_executable_and_code_only_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_output_graph(root)
            with patch("agentkit.graphify.run_command", return_value=self._result()) as run:
                self._client(root).update()
        command = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertEqual(command[0], str(root / "tool env" / "graphify.exe"))
        self.assertIn("--code-only", command)
        self.assertIn("--no-viz", command)
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")
        self.assertEqual(kwargs["env"]["PYTHONUTF8"], "1")
        self.assertEqual(kwargs["env"]["PYTHONIOENCODING"], "utf-8")

    def test_graph_update_preserves_incremental_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ensure_graphify_ignore(root)
            graphify_rebuild_marker(root).unlink()
            self._write_output_graph(root)
            with patch("agentkit.graphify.run_command", return_value=self._result()) as run:
                self._client(root).update()
        command = run.call_args.args[0]
        self.assertIn("--update", command)
        self.assertIn("--code-only", command)

    def test_graph_update_rebuilds_when_ignore_policy_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_output_graph(root)
            with patch("agentkit.graphify.run_command", return_value=self._result()) as run:
                self._client(root).update()
            command = run.call_args.args[0]
            self.assertNotIn("--update", command)
            ignore = (root / ".graphifyignore").read_text(encoding="utf-8")
            self.assertIn(".agent/", ignore)
            self.assertIn(".agents/", ignore)
            self.assertIn("graph.json", ignore)
            self.assertFalse(graphify_rebuild_marker(root).exists())

    def test_failed_full_rebuild_preserves_required_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ensure_graphify_ignore(root)
            self._write_output_graph(root)
            with patch(
                "agentkit.graphify.run_command",
                return_value=self._result(returncode=1),
            ) as run:
                self._client(root).update()
            self.assertNotIn("--update", run.call_args.args[0])
            self.assertTrue(graphify_rebuild_marker(root).is_file())

    def test_graphify_ignore_preserves_user_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ignore = root / ".graphifyignore"
            ignore.write_text("generated/\n", encoding="utf-8")
            self.assertTrue(ensure_graphify_ignore(root))
            first = ignore.read_text(encoding="utf-8")
            self.assertIn("generated/", first)
            self.assertIn(".agent/", first)
            self.assertIn("graph.json", first)
            self.assertFalse(ensure_graphify_ignore(root))
            self.assertEqual(ignore.read_text(encoding="utf-8"), first)
            self.assertTrue(graphify_rebuild_marker(root).is_file())

    def test_successful_update_publishes_root_graph_atomically(self) -> None:
        with tempfile.TemporaryDirectory(prefix="Агент root graph ") as directory:
            root = Path(directory)
            expected = '{"nodes": [{"id": "atomic_write_text"}]}\n'
            self._write_output_graph(root, expected)
            root_graph_path(root).write_text('{"old": true}\n', encoding="utf-8")
            with patch("agentkit.graphify.run_command", return_value=self._result()):
                result = self._client(root).update()
            self.assertIsNotNone(result)
            self.assertTrue(result.passed)
            self.assertIn("published graph.json", result.stdout)
            self.assertEqual(root_graph_path(root).read_text(encoding="utf-8"), expected)
            self.assertEqual(list(root.glob(".graph.json.*.tmp")), [])

    def test_failed_update_preserves_existing_root_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_output_graph(root, '{"new": true}\n')
            root_graph_path(root).write_text('{"stable": true}\n', encoding="utf-8")
            with patch(
                "agentkit.graphify.run_command",
                return_value=self._result(returncode=1),
            ):
                result = self._client(root).update()
            self.assertIsNotNone(result)
            self.assertFalse(result.passed)
            self.assertEqual(
                root_graph_path(root).read_text(encoding="utf-8"),
                '{"stable": true}\n',
            )

    def test_success_without_graph_output_reports_publication_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("agentkit.graphify.run_command", return_value=self._result()):
                result = self._client(root).update()
            self.assertIsNotNone(result)
            self.assertFalse(result.passed)
            self.assertIn("failed to publish root graph.json", result.stderr)
            self.assertTrue(graphify_rebuild_marker(root).is_file())

    def test_graph_query_uses_only_the_original_task_as_question(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = "Где реализовано атомарное сохранение lesson.json?"
            with patch("agentkit.graphify.run_command", return_value=self._result()) as run:
                self._client(root).query(task)
        command = run.call_args.args[0]
        self.assertEqual(command[1:3], ["query", task])
        self.assertNotIn("Identify the smallest relevant code subgraph", " ".join(command))

    def test_doctor_reports_tool_environment_project_skill_and_root_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_default_config(root)
            skill = root / ".agents" / "skills" / "graphify"
            skill.mkdir(parents=True)
            self._write_output_graph(root)
            root_graph_path(root).write_text('{"nodes": []}\n', encoding="utf-8")
            executable = root / "tool env" / "graphify.exe"
            resolution = self._resolution(executable)
            with (
                patch("agentkit.doctor.resolve_graphify_executable", return_value=resolution),
                patch("agentkit.doctor._version", return_value="graphify 0.9.23"),
            ):
                payload = doctor(root)
        graphify = payload["graphify"]
        self.assertTrue(graphify["installed"])
        self.assertEqual(graphify["executable_source"], "agentkit_tool_environment")
        self.assertTrue(graphify["project_skill_installed"])
        self.assertTrue(graphify["output_graph_exists"])
        self.assertTrue(graphify["root_graph_exists"])
        self.assertTrue(str(graphify["root_graph"]).endswith("graph.json"))

    def test_entrypoint_exposes_repair_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = io.StringIO()
            payload = {"attempted": True, "installed": True, "platform": "agents"}
            with (
                patch(
                    "agentkit.entrypoint.install_graphify_project_skill",
                    return_value=payload,
                ) as install,
                redirect_stdout(output),
            ):
                code = entrypoint_main(
                    [
                        "--project-root",
                        str(root),
                        "graph",
                        "install",
                        "--platform",
                        "agents",
                    ]
                )
        self.assertEqual(code, 0)
        install.assert_called_once_with(root.resolve(), platform="agents", required=True)
        self.assertTrue(json.loads(output.getvalue())["installed"])


if __name__ == "__main__":
    unittest.main()
