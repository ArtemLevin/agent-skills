from __future__ import annotations

import json
import sys

from . import cli as core_cli
from .config import configured_project_root
from .evals.cli import efficiency_main, eval_main, quality_history_main
from .evals.resources import ensure_evaluation_files
from .installation import apply_migration, installation_manifest, record_installation_manifest
from .model_runtime import ModelRoutingRunner
from .model_runtime.cli import models_main, providers_main
from .model_runtime.resources import ensure_model_runtime_files
from .quality.ci_cli import main as ci_main
from .quality.cli import main as quality_main
from .quality.hotspot_cli import main as hotspot_context_main
from .quality.resources import ensure_quality_project_files
from .quality.resources_ci import ensure_quality_ci_files
from .quality.resources_gate import ensure_quality_gate_project_files
from .quality.resources_hotspot import ensure_hotspot_context_files
from .quality.resources_routing import ensure_quality_routing_files
from .quality.routing_cli import ROUTING_COMMANDS
from .quality.routing_cli import main as quality_routing_main
from .release_resources import ensure_release_files

_EVALUATION_QUALITY_COMMANDS = {"trend", "regressions", "report"}


def _command_position(argv: list[str]) -> int:
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--project-root":
            index += 2
            continue
        if value.startswith("--project-root="):
            index += 1
            continue
        return index
    return index


def _project_root_arg(argv: list[str]) -> str | None:
    for index, value in enumerate(argv):
        if value == "--project-root" and index + 1 < len(argv):
            return argv[index + 1]
        if value.startswith("--project-root="):
            return value.split("=", 1)[1]
    return None


def _subcommand_argv(argv: list[str], command_index: int) -> list[str]:
    result: list[str] = []
    project_root = _project_root_arg(argv)
    if project_root:
        result.extend(["--project-root", project_root])
    result.extend(argv[command_index + 1 :])
    return result


def _quality_command(argv: list[str]) -> str:
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--project-root":
            index += 2
            continue
        if value.startswith("--project-root="):
            index += 1
            continue
        return value
    return ""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    position = _command_position(args)
    command = args[position] if position < len(args) else ""
    try:
        if command == "ci":
            return ci_main(_subcommand_argv(args, position))
        if command == "eval":
            return eval_main(_subcommand_argv(args, position))
        if command == "efficiency":
            return efficiency_main(_subcommand_argv(args, position))
        if command == "models":
            return models_main(_subcommand_argv(args, position))
        if command == "providers":
            return providers_main(_subcommand_argv(args, position))
        if command == "quality":
            quality_args = _subcommand_argv(args, position)
            quality_command = _quality_command(quality_args)
            if quality_command in _EVALUATION_QUALITY_COMMANDS:
                return quality_history_main(quality_args)
            if quality_command in ROUTING_COMMANDS:
                return quality_routing_main(quality_args)
            return quality_main(quality_args)
        if command == "hotspot-context":
            return hotspot_context_main(_subcommand_argv(args, position))
        core_cli.AgentKitRunner = ModelRoutingRunner
        root = configured_project_root(_project_root_arg(args))
        existing_agent_dir = command == "init" and (root / ".agent").is_dir()
        existing_manifest = (
            installation_manifest(root) if existing_agent_dir else None
        )
        result = core_cli.main(args)
        if command == "init" and result == 0:
            ensure_quality_project_files(root)
            ensure_quality_gate_project_files(root)
            ensure_hotspot_context_files(root)
            ensure_quality_routing_files(root)
            ensure_quality_ci_files(root)
            ensure_evaluation_files(root)
            ensure_model_runtime_files(root)
            ensure_release_files(root)
            if existing_agent_dir:
                apply_migration(root)
            else:
                record_installation_manifest(root)
            if existing_manifest is not None:
                record_installation_manifest(
                    root,
                    overwrite=True,
                    previous_version=str(existing_manifest.get("agentkit_version", "")),
                )
        return result
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(
            json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
