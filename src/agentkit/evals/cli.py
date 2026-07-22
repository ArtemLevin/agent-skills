from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentkit.config import configured_project_root

from .config import load_evaluation_config
from .reports import (
    compare_summaries,
    efficiency_report,
    load_summary,
    quality_regressions,
    quality_trend,
    write_json,
)
from .runner import EvaluationHarness


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _path(project_root: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else project_root / path


def build_eval_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentkit eval",
        description="Run deterministic fixture evaluations and compare engineering outcomes",
    )
    parser.add_argument("--project-root", help="Project directory; defaults to current directory")
    sub = parser.add_subparsers(dest="eval_command", required=True)

    run = sub.add_parser("run", help="Run one evaluation manifest")
    run.add_argument("manifest")
    run.add_argument("--runs", type=int)
    run.add_argument("--evaluation-id")
    run.add_argument("--keep-workspaces", action="store_true")

    suite = sub.add_parser("suite", help="Run sorted manifests from a directory")
    suite.add_argument("directory")
    suite.add_argument("--runs", type=int)
    suite.add_argument("--smoke", action="store_true")
    suite.add_argument("--evaluation-id")
    suite.add_argument("--keep-workspaces", action="store_true")

    compare = sub.add_parser("compare", help="Compare compatible evaluation summaries")
    compare.add_argument("baseline")
    compare.add_argument("current")
    compare.add_argument("--output")
    return parser


def eval_main(argv: list[str] | None = None) -> int:
    args = build_eval_parser().parse_args(argv)
    project_root = configured_project_root(args.project_root)
    config = load_evaluation_config(project_root)
    if args.eval_command == "compare":
        baseline_path = _path(project_root, args.baseline)
        current_path = _path(project_root, args.current)
        comparison = compare_summaries(
            load_summary(baseline_path),
            load_summary(current_path),
            config.regression,
            baseline_name=str(baseline_path),
            current_name=str(current_path),
        )
        payload = comparison.to_dict()
        if args.output:
            write_json(_path(project_root, args.output), payload)
        _print(payload)
        return 4 if comparison.verdict in {"regression", "incomparable"} else 0

    harness = EvaluationHarness(project_root, config)
    if args.eval_command == "run":
        summary, directory = harness.run_manifest(
            _path(project_root, args.manifest),
            repetitions=args.runs,
            evaluation_id=args.evaluation_id,
            keep_workspaces=True if args.keep_workspaces else None,
        )
    else:
        summary, directory = harness.run_suite(
            _path(project_root, args.directory),
            repetitions=args.runs,
            smoke_only=args.smoke,
            evaluation_id=args.evaluation_id,
            keep_workspaces=True if args.keep_workspaces else None,
        )
    _print(
        {
            "evaluation_directory": str(directory),
            "summary": summary.to_dict(),
        }
    )
    return 0 if summary.failed_runs == 0 and summary.error_runs == 0 else 4


def build_quality_history_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentkit quality")
    parser.add_argument("--project-root", help="Project directory; defaults to current directory")
    sub = parser.add_subparsers(dest="history_command", required=True)
    trend = sub.add_parser("trend", help="Show recent quality evaluation history")
    trend.add_argument("--limit", type=int)
    regressions = sub.add_parser("regressions", help="Show detected evaluation regressions")
    regressions.add_argument("--limit", type=int)
    report = sub.add_parser("report", help="Show combined quality evaluation report")
    report.add_argument("--limit", type=int)
    return parser


def quality_history_main(argv: list[str] | None = None) -> int:
    args = build_quality_history_parser().parse_args(argv)
    project_root = configured_project_root(args.project_root)
    config = load_evaluation_config(project_root)
    limit = args.limit if args.limit is not None else config.report_limit
    if limit <= 0:
        raise ValueError("--limit must be positive")
    if args.history_command == "trend":
        payload = quality_trend(project_root, limit=limit)
    elif args.history_command == "regressions":
        payload = quality_regressions(
            project_root,
            limit=limit,
            thresholds=config.regression,
        )
    else:
        payload = {
            "version": 1,
            "trend": quality_trend(project_root, limit=limit),
            "regressions": quality_regressions(
                project_root,
                limit=limit,
                thresholds=config.regression,
            ),
        }
    _print(payload)
    return 0


def build_efficiency_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentkit efficiency")
    parser.add_argument("--project-root", help="Project directory; defaults to current directory")
    sub = parser.add_subparsers(dest="efficiency_command", required=True)
    report = sub.add_parser("report", help="Show recent measured and unknown efficiency data")
    report.add_argument("--limit", type=int)
    return parser


def efficiency_main(argv: list[str] | None = None) -> int:
    args = build_efficiency_parser().parse_args(argv)
    project_root = configured_project_root(args.project_root)
    config = load_evaluation_config(project_root)
    limit = args.limit if args.limit is not None else config.report_limit
    if limit <= 0:
        raise ValueError("--limit must be positive")
    _print(efficiency_report(project_root, limit=limit))
    return 0
