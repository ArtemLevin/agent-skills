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
    install_graphify_project_skill,
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
        self.assertEqual(command[0], str(executable))
        self.assertEqual(command[1:], ["install", "--project", "--platform", "agents"])
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

    def test_graph_client_uses_absolute_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "tool env" / "graphify.exe"
            policy = CommandPolicy(["graphify"], [])
            result = CommandResult(
                command=[],
                returncode=0,
                stdout="ok",
                stderr="",
                duration_seconds=0.1,
            )
            with patch("agentkit.graphify.run_command", return_value=result) as run:
                client = GraphifyClient(
                    root,
                    GraphifyConfig(),
                    policy,
                    resolution=self._resolution(executable),
                )
                client.update()
        command = run.call_args.args[0]
        self.assertEqual(command[0], str(executable))
        self.assertIn("--no-viz", command)

    def test_doctor_reports_tool_environment_and_project_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_default_config(root)
            skill = root / ".agents" / "skills" / "graphify"
            skill.mkdir(parents=True)
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

    def test_entrypoint_exposes_repair_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = io.StringIO()
            payload = {"attempted": True, "installed": True, "platform": "agents"}
            with (
                patch("agentkit.entrypoint.install_graphify_project_skill", return_value=payload) as install,
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
