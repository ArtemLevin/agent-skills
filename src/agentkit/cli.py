from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .commands import CommandPolicy
from .config import configured_project_root, load_config
from .context_cache import ContextCache
from .context_compiler import ContextCompiler, PHASES
from .doctor import doctor
from .graphify import GraphifyClient
from .init_project import initialize_project
from .models import RunMode
from .project_profile import load_or_create_profile
from .reporting import aggregate_report, load_budget_status, load_usage
from .runner import AgentKitError, AgentKitRunner, RunRequest
from .triage import classify_task
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
    parser.add_argument(
        "--task-file",
        help="UTF-8 file containing the task",
    )
    parser.add_argument(
        "--mode",
        choices=[item.value for item in RunMode],
        default="auto",
    )
    parser.add_argument(
        "--agent",
        help="Override selected agent platform",
    )
    parser.add_argument(
        "--approve-deep",
        action="store_true",
        help="Authorize deep-mode code execution",
    )
    parser.add_argument("--skip-graph", action="store_true")
    parser.add_argument("--dry-run", action="store_true")


def _add_context_task_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument("--task", help="Task text")
    parser.add_argument(
        "--task-file",
        help="UTF-8 file containing the task",
    )
    parser.add_argument(
        "--phase",
        choices=PHASES,
        default="implementation",
    )
    parser.add_argument(
        "--mode",
        choices=[item.value for item in RunMode],
        default="auto",
    )
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        help="Explicit selected skill; repeatable",
    )
    parser.add_argument(
        "--output",
        help="Write compiled Markdown to this path",
    )
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--refresh-profile", action="store_true")
    parser.add_argument("--metadata-only", action="store_true")


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

    init = sub.add_parser(
        "init",
        help="Install AgentKit project files",
    )
    init.add_argument("--force", action="store_true")
    init.add_argument(
        "--platform",
        default="agents",
        help="Graphify skill target platform",
    )
    init.add_argument(
        "--skip-graphify-install",
        action="store_true",
    )

    run = sub.add_parser(
        "run",
        help="Execute the full supervised-autopilot workflow",
    )
    _add_task_arguments(run)

    plan = sub.add_parser(
        "plan",
        help="Build context and ask the agent for a non-mutating plan",
    )
    _add_task_arguments(plan)

    graph = sub.add_parser(
        "graph",
        help="Manage Graphify context",
    )
    graph_sub = graph.add_subparsers(
        dest="graph_command",
        required=True,
    )
    graph_sub.add_parser("update")
    query = graph_sub.add_parser("query")
    query.add_argument("question")

    profile = sub.add_parser(
        "profile",
        help="Build or inspect the deterministic project profile",
    )
    profile_sub = profile.add_subparsers(
        dest="profile_command",
        required=True,
    )
    profile_sub.add_parser("show")
    profile_sub.add_parser("refresh")

    context = sub.add_parser(
        "context",
        help="Compile phase-specific minimal agent context",
    )
    context_sub = context.add_subparsers(
        dest="context_command",
        required=True,
    )
    compile_context = context_sub.add_parser("compile")
    _add_context_task_arguments(compile_context)

    cache = sub.add_parser(
        "cache",
        help="Inspect and maintain the SQLite context cache",
    )
    cache_sub = cache.add_subparsers(
        dest="cache_command",
        required=True,
    )
    cache_sub.add_parser("stats")
    cache_list = cache_sub.add_parser("list")
    cache_list.add_argument("--namespace")
    cache_list.add_argument("--limit", type=int, default=20)
    cache_prune = cache_sub.add_parser("prune")
    cache_prune.add_argument("--max-age-days", type=int)
    cache_clear = cache_sub.add_parser("clear")
    cache_clear.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion of every cache entry",
    )

    sub.add_parser(
        "check",
        help="Run configured or auto-discovered verification",
    )
    sub.add_parser(
        "doctor",
        help="Check local installation and project readiness",
    )
    sub.add_parser(
        "status",
        help="Show latest AgentKit run status",
    )

    usage = sub.add_parser(
        "usage",
        help="Show per-phase telemetry for one run",
    )
    usage.add_argument("--run-id", default="latest")

    budget = sub.add_parser(
        "budget",
        help="Evaluate configured budgets for one run",
    )
    budget.add_argument("--run-id", default="latest")

    report = sub.add_parser(
        "report",
        help="Aggregate usage and readiness across recent runs",
    )
    report.add_argument("--limit", type=int, default=20)
    return parser


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _resolve_project_path(
    project_root: Path,
    raw: str,
) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else project_root / path


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
                    install_graphify_skill=(
                        not args.skip_graphify_install
                    ),
                )
            )
            return 0
        if args.command == "doctor":
            payload = doctor(project_root)
            _print(payload)
            return (
                0
                if payload["git_repository"]
                and payload["config_ok"]
                else 2
            )
        if args.command == "status":
            latest = project_root / ".agent" / "state" / "latest"
            if not latest.is_file():
                _print({"status": "no_runs"})
                return 1
            run_id = latest.read_text(encoding="utf-8").strip()
            completion = (
                project_root
                / ".agent"
                / "state"
                / "runs"
                / run_id
                / "completion.json"
            )
            payload = (
                json.loads(completion.read_text(encoding="utf-8"))
                if completion.is_file()
                else {"status": "incomplete"}
            )
            _print({"run_id": run_id, "completion": payload})
            return 0
        if args.command == "usage":
            _print(load_usage(project_root, args.run_id))
            return 0
        if args.command == "report":
            _print(aggregate_report(project_root, limit=args.limit))
            return 0

        config = load_config(project_root)
        policy = CommandPolicy(
            config.security.allowed_executables,
            config.security.denied_substrings,
        )
        if args.command == "profile":
            profile_path = _resolve_project_path(
                project_root,
                config.context.profile_path,
            )
            profile, refreshed = load_or_create_profile(
                project_root,
                profile_path,
                refresh=args.profile_command == "refresh",
                max_files=config.context.max_profile_files,
            )
            _print(
                {
                    "refreshed": refreshed,
                    "path": str(profile_path),
                    "profile": profile.to_dict(),
                }
            )
            return 0
        if args.command == "context":
            task = _task_from_args(args)
            selected_skills = list(args.skill)
            if not selected_skills:
                selected_skills = classify_task(
                    task,
                    RunMode(args.mode),
                ).selected_skills
            compiler = ContextCompiler(
                project_root,
                config.context,
            )
            compiled = compiler.compile(
                task=task,
                phase=args.phase,
                mode=args.mode,
                selected_skills=selected_skills,
                refresh_profile=args.refresh_profile,
                use_cache=not args.no_cache,
            )
            output = compiler.write(
                compiled,
                Path(args.output) if args.output else None,
            )
            payload = compiled.to_dict(
                include_content=not args.metadata_only
            )
            payload["output_path"] = str(output)
            _print(payload)
            return 0
        if args.command == "cache":
            cache_path = _resolve_project_path(
                project_root,
                config.context.cache_path,
            )
            cache = ContextCache(cache_path)
            if args.cache_command == "stats":
                _print(cache.stats())
                return 0
            if args.cache_command == "list":
                _print(
                    {
                        "path": str(cache_path),
                        "entries": cache.list_entries(
                            namespace=args.namespace,
                            limit=args.limit,
                        ),
                    }
                )
                return 0
            if args.cache_command == "prune":
                days = (
                    config.context.stale_after_days
                    if args.max_age_days is None
                    else args.max_age_days
                )
                _print(
                    cache.prune(max_age_days=days)
                    | {"path": str(cache_path)}
                )
                return 0
            if not args.yes:
                raise AgentKitError(
                    "Refusing to clear cache without --yes"
                )
            _print(cache.clear() | {"path": str(cache_path)})
            return 0
        if args.command == "budget":
            payload = load_budget_status(
                project_root,
                config.budget,
                args.run_id,
            )
            _print(payload)
            return 0 if payload["status"]["allowed"] else 5
        if args.command == "check":
            results = run_checks(
                project_root,
                config.verification,
                policy,
            )
            _print([item.to_dict() for item in results])
            return (
                0
                if results and all(item.passed for item in results)
                else 4
            )
        if args.command == "graph":
            client = GraphifyClient(
                project_root,
                config.graphify,
                policy,
            )
            result = (
                client.update()
                if args.graph_command == "update"
                else client.query(args.question)
            )
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
            outcome = AgentKitRunner(
                project_root,
                config=config,
            ).run(request)
            _print(
                {
                    "run_id": outcome.run_id,
                    "stage": outcome.stage.value,
                    "message": outcome.message,
                    "completion": (
                        outcome.completion.to_dict()
                        if outcome.completion
                        else None
                    ),
                }
            )
            return outcome.exit_code
    except (
        AgentKitError,
        FileNotFoundError,
        ValueError,
        RuntimeError,
    ) as exc:
        print(f"agentkit: {exc}", file=sys.stderr)
        return 2
    return 2
