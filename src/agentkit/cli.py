from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .commands import CommandPolicy
from .config import configured_project_root, load_config
from .doctor import doctor
from .graphify import GraphifyClient
from .init_project import initialize_project
from .models import RunMode
from .runner import AgentKitError, AgentKitRunner, RunRequest
from .verification import run_checks


def _task_from_args(args: argparse.Namespace) -> str:
    if args.task and args.task_file:
        raise AgentKitError("Use either --task or --task-file, not both")
    if args.task_file:
        return Path(args.task_file).read_text(encoding="utf-8")
    if args.task:
        return args.task
    raise AgentKitError("Provide --task or --task-file")


def _add_task_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task", help="Task text")
    parser.add_argument("--task-file", help="UTF-8 file containing the task")
    parser.add_argument("--mode", choices=[item.value for item in RunMode], default="auto")
    parser.add_argument("--agent", help="Override selected agent platform")
    parser.add_argument("--approve-deep", action="store_true", help="Authorize deep-mode code execution")
    parser.add_argument("--skip-graph", action="store_true")
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentkit",
        description="Graph-aware supervised autopilot for coding agents",
    )
    parser.add_argument(
        "--project-root",
        help="Project directory; defaults to current working directory",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Install AgentKit project files")
    init.add_argument("--force", action="store_true")
    init.add_argument("--platform", default="agents", help="Graphify skill target platform")
    init.add_argument("--skip-graphify-install", action="store_true")

    run = sub.add_parser("run", help="Execute the full supervised-autopilot workflow")
    _add_task_arguments(run)

    plan = sub.add_parser("plan", help="Build context and ask the agent for a non-mutating plan")
    _add_task_arguments(plan)

    graph = sub.add_parser("graph", help="Manage Graphify context")
    graph_sub = graph.add_subparsers(dest="graph_command", required=True)
    graph_sub.add_parser("update")
    query = graph_sub.add_parser("query")
    query.add_argument("question")

    sub.add_parser("check", help="Run configured or auto-discovered verification")
    sub.add_parser("doctor", help="Check local installation and project readiness")
    sub.add_parser("status", help="Show latest AgentKit run status")
    return parser


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = configured_project_root(args.project_root)
    try:
        if args.command == "init":
            _print(
                initialize_project(
                    project_root,
                    force=args.force,
                    platform=args.platform,
                    install_graphify_skill=not args.skip_graphify_install,
                )
            )
            return 0
        if args.command == "doctor":
            payload = doctor(project_root)
            _print(payload)
            return 0 if payload["git_repository"] and payload["config_ok"] else 2
        if args.command == "status":
            latest = project_root / ".agent" / "state" / "latest"
            if not latest.is_file():
                _print({"status": "no_runs"})
                return 1
            run_id = latest.read_text(encoding="utf-8").strip()
            completion = project_root / ".agent" / "state" / "runs" / run_id / "completion.json"
            payload = (
                json.loads(completion.read_text(encoding="utf-8"))
                if completion.is_file()
                else {"status": "incomplete"}
            )
            _print({"run_id": run_id, "completion": payload})
            return 0

        config = load_config(project_root)
        policy = CommandPolicy(
            config.security.allowed_executables,
            config.security.denied_substrings,
        )
        if args.command == "check":
            results = run_checks(project_root, config.verification, policy)
            _print([item.to_dict() for item in results])
            return 0 if results and all(item.passed for item in results) else 4
        if args.command == "graph":
            client = GraphifyClient(project_root, config.graphify, policy)
            result = client.update() if args.graph_command == "update" else client.query(args.question)
            if result is None:
                _print({"status": "unavailable"})
                return 2
            _print(result.to_dict())
            return 0 if result.passed else result.returncode or 2
        if args.command in {"run", "plan"}:
            request = RunRequest(
                task=_task_from_args(args),
                mode=RunMode(args.mode),
                agent_override=args.agent,
                plan_only=args.command == "plan",
                dry_run=args.dry_run,
                approve_deep=args.approve_deep,
                skip_graph=args.skip_graph,
            )
            outcome = AgentKitRunner(project_root, config=config).run(request)
            _print(
                {
                    "run_id": outcome.run_id,
                    "stage": outcome.stage.value,
                    "message": outcome.message,
                    "completion": outcome.completion.to_dict() if outcome.completion else None,
                }
            )
            return outcome.exit_code
    except (AgentKitError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"agentkit: {exc}", file=sys.stderr)
        return 2
    return 2
