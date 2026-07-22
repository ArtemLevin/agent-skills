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

from .comparison import compare_snapshots
from .config import load_quality_config
from .gate import evaluate_quality_gate
from .lifecycle import QualityLifecycle
from .gate_models import QualityDiff
from .models import QualitySnapshot
from .service import QualityService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentkit quality",
        description="Quality diagnostics, comparison, and regression gates",
    )
    parser.add_argument("--project-root", help="Project directory; defaults to current directory")
    sub = parser.add_subparsers(dest="quality_command", required=True)

    sub.add_parser("doctor", help="Check provider availability and language support")
    baseline = sub.add_parser("baseline", help="Capture the configured quality baseline")
    baseline.add_argument("--no-cache", action="store_true")

    analyze = sub.add_parser("analyze", help="Create a quality snapshot")
    analyze.add_argument("--stage", choices=("before", "after"), default="before")
    analyze.add_argument("--details", action="store_true", help="Force bounded detailed analysis")
    analyze.add_argument("--no-cache", action="store_true", help="Disable snapshot cache for this call")

    compare = sub.add_parser("compare", help="Compare quality-before.json with quality-after.json")
    compare.add_argument("--run-id", default="latest")

    gate = sub.add_parser("gate", help="Evaluate configured quality thresholds")
    gate.add_argument("--run-id", default="latest")

    cycle = sub.add_parser("cycle", help="Capture baseline, analyze current state, compare, and gate")
    cycle.add_argument("--no-cache", action="store_true")

    hotspots = sub.add_parser("hotspots", help="Show bounded hotspots from an existing run")
    hotspots.add_argument("--run-id", default="latest")
    hotspots.add_argument("--stage", choices=("before", "after"), default="before")

    show = sub.add_parser("show", help="Show a quality artifact from an existing run")
    show.add_argument("--run-id", default="latest")
    show.add_argument(
        "--artifact",
        choices=("before", "after", "diff", "gate", "provider"),
        default="before",
    )
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


def _run_directory(project_root: Path, run_id: str) -> tuple[str, Path]:
    resolved = _resolve_run_id(project_root, run_id)
    return resolved, project_root / ".agent" / "state" / "runs" / resolved


def _artifact(project_root: Path, run_id: str, name: str) -> tuple[str, dict[str, object]]:
    resolved, directory = _run_directory(project_root, run_id)
    path = directory / name
    if not path.is_file():
        raise FileNotFoundError(f"Quality artifact not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Quality artifact must be a JSON object: {path}")
    return resolved, payload


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _effective_config(config: object, *, no_cache: bool):
    return replace(config, cache_enabled=False) if no_cache else config


def _observer(ledger: UsageLedger, directory: Path, provider: str):
    def observe(phase: str, result: CommandResult) -> None:
        ledger.record(phase=phase, kind="tool", result=result, provider=provider)
        ledger.save(directory / "usage.json")
    return observe


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = configured_project_root(args.project_root)
    core_config = load_config(project_root)
    quality_config = load_quality_config(project_root)

    if args.quality_command == "doctor":
        status = QualityService(
            project_root,
            quality_config,
            core_config.context,
            core_config.security,
        ).doctor()
        _print(status.to_dict())
        return 0 if status.usable else 2

    artifact_names = {
        "before": "quality-before.json",
        "after": "quality-after.json",
        "diff": "quality-diff.json",
        "gate": "quality-gate.json",
        "provider": "quality-provider.json",
    }
    if args.quality_command == "show":
        run_id, payload = _artifact(project_root, args.run_id, artifact_names[args.artifact])
        _print({"run_id": run_id, "artifact": args.artifact, "payload": payload})
        return 0

    if args.quality_command == "hotspots":
        name = "quality-hotspots.json" if args.stage == "before" else "quality-after-hotspots.json"
        run_id, payload = _artifact(project_root, args.run_id, name)
        _print({"run_id": run_id, "stage": args.stage, "hotspots": payload})
        return 0

    if args.quality_command == "compare":
        run_id, directory = _run_directory(project_root, args.run_id)
        before = QualitySnapshot.from_dict(_artifact(project_root, run_id, "quality-before.json")[1])
        after = QualitySnapshot.from_dict(_artifact(project_root, run_id, "quality-after.json")[1])
        diff = compare_snapshots(
            before,
            after,
            baseline_strategy=quality_config.baseline_strategy,
        )
        path = _write(directory / "quality-diff.json", diff.to_dict())
        _print({"run_id": run_id, "path": str(path), "diff": diff.to_dict()})
        return 0

    if args.quality_command == "gate":
        run_id, directory = _run_directory(project_root, args.run_id)
        after = QualitySnapshot.from_dict(_artifact(project_root, run_id, "quality-after.json")[1])
        diff = QualityDiff.from_dict(_artifact(project_root, run_id, "quality-diff.json")[1])
        result = evaluate_quality_gate(quality_config, after, diff)
        path = _write(directory / "quality-gate.json", result.to_dict())
        _print({"run_id": run_id, "path": str(path), "gate": result.to_dict()})
        return 0 if result.allowed else 6

    run_id, directory = _new_quality_run(project_root)
    no_cache = bool(getattr(args, "no_cache", False))
    effective = _effective_config(quality_config, no_cache=no_cache)
    ledger = UsageLedger(run_id=run_id, provider=effective.provider)
    observer = _observer(ledger, directory, effective.provider)
    ledger.save(directory / "usage.json")
    lifecycle = QualityLifecycle(
        project_root,
        effective,
        core_config.context,
        core_config.security,
        observer=observer,
    )

    if args.quality_command == "baseline":
        baseline = lifecycle.capture_baseline(directory)
        _print({
            "run_id": run_id,
            "strategy": baseline.strategy,
            "snapshot": baseline.result.snapshot.to_dict(),
            "warnings": list(baseline.warnings),
        })
        return 2 if effective.required and not baseline.result.snapshot.usable else 0

    if args.quality_command == "analyze":
        if args.stage == "after":
            result = lifecycle.analyze_after(directory, force_details=args.details)
        else:
            result = QualityService(
                project_root,
                effective,
                core_config.context,
                core_config.security,
                observer=observer,
                phase="quality_before",
            ).analyze(directory, force_details=args.details)
        _print({
            "run_id": run_id,
            "stage": args.stage,
            "snapshot": result.snapshot.to_dict(),
            "provider": result.provider_status.to_dict(),
            "artifacts": {
                "snapshot": str(result.artifacts.snapshot_path),
                "hotspots": str(result.artifacts.hotspots_path),
                "provider": str(result.artifacts.provider_path),
            },
        })
        return 2 if effective.required and not result.snapshot.usable else 0

    baseline = lifecycle.capture_baseline(directory)
    cycle = lifecycle.finalize(directory, baseline)
    _print({
        "run_id": run_id,
        "baseline_strategy": baseline.strategy,
        "before": baseline.result.snapshot.to_dict(),
        "after": cycle.current.snapshot.to_dict(),
        "diff": cycle.diff.to_dict(),
        "gate": cycle.gate.to_dict(),
    })
    return 0 if cycle.gate.allowed else 6
