from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agentkit.config import configured_project_root, load_config
from agentkit.models import CommandResult
from agentkit.telemetry import UsageLedger

from .config import load_quality_config
from .service import QualityService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentkit quality",
        description="Quality diagnostics provider",
    )
    parser.add_argument("--project-root", help="Project directory; defaults to current directory")
    sub = parser.add_subparsers(dest="quality_command", required=True)
    sub.add_parser("doctor", help="Check provider availability and language support")
    analyze = sub.add_parser("analyze", help="Create a report-only quality snapshot")
    analyze.add_argument("--details", action="store_true", help="Force bounded detailed analysis")
    analyze.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable snapshot cache for this call",
    )
    hotspots = sub.add_parser("hotspots", help="Show bounded hotspots from an existing run")
    hotspots.add_argument("--run-id", default="latest")
    show = sub.add_parser("show", help="Show a quality snapshot from an existing run")
    show.add_argument("--run-id", default="latest")
    return parser


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _new_quality_run(project_root: Path) -> tuple[str, Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"quality-{stamp}-{uuid4().hex[:8]}"
    directory = project_root / ".agent" / "state" / "runs" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    pointer = project_root / ".agent" / "state" / "quality-latest"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(run_id, encoding="utf-8")
    return run_id, directory


def _resolve_run_id(project_root: Path, run_id: str) -> str:
    if run_id != "latest":
        return run_id
    quality_latest = project_root / ".agent" / "state" / "quality-latest"
    if quality_latest.is_file():
        return quality_latest.read_text(encoding="utf-8").strip()
    latest = project_root / ".agent" / "state" / "latest"
    if latest.is_file():
        return latest.read_text(encoding="utf-8").strip()
    raise FileNotFoundError("No AgentKit quality runs exist")


def _artifact(project_root: Path, run_id: str, name: str) -> tuple[str, dict[str, object]]:
    resolved = _resolve_run_id(project_root, run_id)
    path = project_root / ".agent" / "state" / "runs" / resolved / name
    if not path.is_file():
        raise FileNotFoundError(f"Quality artifact not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Quality artifact must be a JSON object: {path}")
    return resolved, payload


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = configured_project_root(args.project_root)
    core_config = load_config(project_root)
    quality_config = load_quality_config(project_root)
    service = QualityService(
        project_root,
        quality_config,
        core_config.context,
        core_config.security,
    )
    if args.quality_command == "doctor":
        status = service.doctor()
        _print(status.to_dict())
        return 0 if status.usable else 2
    if args.quality_command == "show":
        run_id, payload = _artifact(project_root, args.run_id, "quality-before.json")
        _print({"run_id": run_id, "snapshot": payload})
        return 0
    if args.quality_command == "hotspots":
        run_id, payload = _artifact(project_root, args.run_id, "quality-hotspots.json")
        _print({"run_id": run_id, "hotspots": payload})
        return 0

    run_id, directory = _new_quality_run(project_root)
    ledger = UsageLedger(run_id=run_id, provider=quality_config.provider)

    def observer(phase: str, result: CommandResult) -> None:
        ledger.record(phase=phase, kind="tool", result=result, provider=quality_config.provider)
        ledger.save(directory / "usage.json")

    effective = quality_config
    if args.no_cache:
        effective = replace(quality_config, cache_enabled=False)
    service = QualityService(
        project_root,
        effective,
        core_config.context,
        core_config.security,
        observer=observer,
        phase="quality_before",
    )
    ledger.save(directory / "usage.json")
    result = service.analyze(directory, force_details=args.details)
    payload = {
        "run_id": run_id,
        "snapshot": result.snapshot.to_dict(),
        "provider": result.provider_status.to_dict(),
        "artifacts": {
            "snapshot": str(result.artifacts.snapshot_path),
            "hotspots": str(result.artifacts.hotspots_path),
            "provider": str(result.artifacts.provider_path),
            "raw_stdout": str(result.artifacts.raw_stdout_path)
            if result.artifacts.raw_stdout_path
            else None,
            "raw_stderr": str(result.artifacts.raw_stderr_path)
            if result.artifacts.raw_stderr_path
            else None,
        },
    }
    _print(payload)
    if quality_config.required and not result.snapshot.usable:
        return 2
    return 0
