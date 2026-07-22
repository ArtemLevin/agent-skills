from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentkit.config import configured_project_root, load_config
from agentkit.models import RunMode
from agentkit.triage import classify_task

from .hotspot_context import HotspotContextCompiler
from .routing import QualityRoute, route_quality
from .routing_config import load_quality_routing_config
from .verification_plan import build_verification_plan


ROUTING_COMMANDS = {"triage", "plan-checks", "explain-route"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentkit quality",
        description="Quality-aware triage and verification planning",
    )
    parser.add_argument("--project-root", help="Project directory; defaults to current directory")
    sub = parser.add_subparsers(dest="quality_command", required=True)

    for name, help_text in (
        ("triage", "Refine task triage using scoped quality evidence"),
        ("plan-checks", "Create a quality-aware verification plan"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--task")
        command.add_argument("--task-file")
        command.add_argument("--mode", choices=[item.value for item in RunMode], default="auto")
        command.add_argument("--run-id", default="latest")
        command.add_argument("--limit", type=int)

    explain = sub.add_parser("explain-route", help="Show a persisted quality route")
    explain.add_argument("--run-id", default="latest")
    return parser


def _task(args: argparse.Namespace) -> str:
    if getattr(args, "task", None):
        return str(args.task)
    task_file = getattr(args, "task_file", None)
    if task_file:
        return Path(task_file).read_text(encoding="utf-8")
    raise ValueError("Provide --task or --task-file")


def _resolve_run_id(project_root: Path, run_id: str) -> str:
    if run_id != "latest":
        return run_id
    for pointer in ("quality-latest", "latest"):
        path = project_root / ".agent" / "state" / pointer
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
    raise FileNotFoundError("No AgentKit run containing quality evidence exists")


def _run_dir(project_root: Path, run_id: str) -> tuple[str, Path]:
    resolved = _resolve_run_id(project_root, run_id)
    directory = project_root / ".agent" / "state" / "runs" / resolved
    if not directory.is_dir():
        raise FileNotFoundError(f"AgentKit run does not exist: {directory}")
    return resolved, directory


def _write(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _route(
    project_root: Path,
    *,
    task: str,
    mode: RunMode,
    run_id: str,
    limit: int | None,
) -> tuple[str, Path, QualityRoute]:
    resolved, directory = _run_dir(project_root, run_id)
    core = load_config(project_root)
    context = HotspotContextCompiler(project_root, core.context).compile(
        task=task,
        run_id=resolved,
        limit=limit,
    )
    snapshot_path = project_root / context.source_snapshot
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        raise ValueError("Quality snapshot must be a JSON object")
    graph_output = ""
    graph_path = directory / "graph.json"
    if graph_path.is_file():
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        if isinstance(graph_payload, dict):
            graph_output = str(graph_payload.get("output", ""))
    route = route_quality(
        task=task,
        base_triage=classify_task(task, mode),
        context=context,
        snapshot_payload=snapshot,
        graph_output=graph_output,
        config=load_quality_routing_config(project_root),
    )
    _write(directory / "quality-route.json", route.to_dict())
    return resolved, directory, route


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = configured_project_root(args.project_root)
    if args.quality_command == "explain-route":
        run_id, directory = _run_dir(project_root, args.run_id)
        path = directory / "quality-route.json"
        if not path.is_file():
            raise FileNotFoundError(f"Quality route not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps({"run_id": run_id, "route": payload}, ensure_ascii=False, indent=2))
        return 0

    task = _task(args)
    run_id, directory, route = _route(
        project_root,
        task=task,
        mode=RunMode(args.mode),
        run_id=args.run_id,
        limit=args.limit,
    )
    if args.quality_command == "triage":
        print(json.dumps({"run_id": run_id, "route": route.to_dict()}, ensure_ascii=False, indent=2))
        return 0

    core = load_config(project_root)
    plan = build_verification_plan(project_root, core.verification, route)
    _write(directory / "verification-plan.json", plan.to_dict())
    print(
        json.dumps(
            {"run_id": run_id, "route": route.to_dict(), "verification_plan": plan.to_dict()},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
