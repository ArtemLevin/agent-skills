from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentkit.config import configured_project_root, load_config

from .ci_config import (
    ensure_quality_ci_config,
    load_quality_ci_config,
)
from .ci_runner import QualityCIRunner
from .ci_summary import (
    github_annotations,
    load_quality_summary_inputs,
    render_quality_summary,
    resolve_run_directory,
)
from .ci_workflow import (
    install_quality_workflow,
    preview_quality_workflow,
)
from .config import load_quality_config
from .service import QualityService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentkit ci",
        description="Generate and run reproducible AgentKit quality CI",
    )
    parser.add_argument(
        "--project-root",
        help="Project directory; defaults to current directory",
    )
    top = parser.add_subparsers(dest="ci_domain", required=True)
    quality = top.add_parser("quality", help="Quality CI workflow and local runner")
    commands = quality.add_subparsers(dest="ci_command", required=True)

    install = commands.add_parser(
        "install",
        help="Generate .github/workflows/agentkit-quality.yml",
    )
    install.add_argument("--force", action="store_true")

    commands.add_parser(
        "preview",
        help="Render the workflow and report whether installation would overwrite it",
    )
    commands.add_parser(
        "validate",
        help="Validate quality CI configuration and provider availability",
    )

    run_local = commands.add_parser(
        "run-local",
        help="Run the same merge-base quality lifecycle used by GitHub Actions",
    )
    run_local.add_argument("--base-ref")
    run_local.add_argument("--run-id")

    summary = commands.add_parser(
        "summary",
        help="Render a bounded Markdown summary for an existing run",
    )
    summary.add_argument("--run-id", default="latest")
    summary.add_argument("--output")
    summary.add_argument("--append", action="store_true")
    summary.add_argument("--annotations", action="store_true")
    return parser


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _write_output(path: Path, content: str, *, append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as handle:
        handle.write(content)


def _existing_failure_summary(project_root: Path, run_id: str) -> tuple[str, str]:
    resolved, directory = resolve_run_directory(project_root, run_id)
    for path in (
        directory / "quality-summary.md",
        directory / "ci-artifacts" / "quality-summary.md",
    ):
        if path.is_file():
            return resolved, path.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"No quality summary or diff/gate artifacts exist in {directory}"
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = configured_project_root(args.project_root)
    core_config = load_config(project_root)
    quality_config = load_quality_config(project_root)
    ci_config = load_quality_ci_config(project_root)

    if args.ci_command == "install":
        ensure_quality_ci_config(project_root)
        ci_config = load_quality_ci_config(project_root)
        path, changed = install_quality_workflow(
            project_root,
            ci_config,
            force=args.force,
        )
        _print(
            {
                "path": str(path),
                "changed": changed,
                "permissions": {"contents": "read"},
            }
        )
        return 0

    if args.ci_command == "preview":
        _print(preview_quality_workflow(project_root, ci_config))
        return 0

    if args.ci_command == "validate":
        if not ci_config.enabled:
            raise RuntimeError("quality.ci.enabled=false")
        if not quality_config.enabled:
            raise RuntimeError("quality.enabled=false")
        status = QualityService(
            project_root,
            quality_config,
            core_config.context,
            core_config.security,
        ).doctor()
        payload = {
            "quality_ci": {
                "enabled": ci_config.enabled,
                "workflow_path": ci_config.workflow_path,
                "base_branch": ci_config.base_branch,
                "artifact_retention_days": ci_config.artifact_retention_days,
                "permissions": {"contents": "read"},
            },
            "provider": status.to_dict(),
        }
        _print(payload)
        if quality_config.required and not status.usable:
            return 2
        return 0

    if args.ci_command == "run-local":
        base_ref = args.base_ref or ci_config.base_branch
        result = QualityCIRunner(
            project_root,
            core_config,
            quality_config,
            ci_config,
        ).run(
            base_ref=base_ref,
            run_id=args.run_id,
        )
        _print(result.to_dict())
        return result.exit_code

    try:
        resolved, _, diff, gate = load_quality_summary_inputs(
            project_root,
            args.run_id,
        )
        content = render_quality_summary(diff, gate, quality_config)
        annotations = github_annotations(diff, gate) if args.annotations else ()
    except FileNotFoundError:
        resolved, content = _existing_failure_summary(
            project_root,
            args.run_id,
        )
        annotations = ()

    if args.output:
        output = Path(args.output).expanduser()
        if not output.is_absolute():
            output = project_root / output
        _write_output(output, content, append=args.append)
    else:
        print(content, end="")
    for annotation in annotations:
        print(annotation)
    return 0
