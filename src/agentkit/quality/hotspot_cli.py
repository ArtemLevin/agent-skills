from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentkit.config import configured_project_root, load_config

from .hotspot_context import HotspotContextCompiler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentkit hotspot-context", description="Compile bounded quality-aware repository context")
    parser.add_argument("--project-root", help="Project directory; defaults to current directory")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile", help="Rank quality hotspots for a task")
    compile_cmd.add_argument("--task")
    compile_cmd.add_argument("--task-file")
    compile_cmd.add_argument("--run-id", default="latest")
    compile_cmd.add_argument("--limit", type=int)
    compile_cmd.add_argument("--output")
    compile_cmd.add_argument("--no-cache", action="store_true")
    explain = sub.add_parser("explain", help="Show one ranked candidate with evidence")
    explain.add_argument("--task", required=True)
    explain.add_argument("--file", required=True)
    explain.add_argument("--symbol", default="")
    explain.add_argument("--run-id", default="latest")
    return parser


def _task(args: argparse.Namespace) -> str:
    if args.task:
        return str(args.task)
    if args.task_file:
        return Path(args.task_file).read_text(encoding="utf-8")
    raise ValueError("Provide --task or --task-file")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = configured_project_root(args.project_root)
    compiler = HotspotContextCompiler(root, load_config(root).context)
    if args.command == "compile":
        result = compiler.compile(task=_task(args), run_id=args.run_id, limit=args.limit, use_cache=not args.no_cache)
        output = Path(args.output) if args.output else root / ".agent" / "state" / "contexts" / f"hotspot-{result.cache_key}.md"
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.content, encoding="utf-8")
        payload = result.to_dict(include_content=False)
        payload["output"] = str(output)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    result = compiler.compile(task=args.task, run_id=args.run_id)
    matches = [item.to_dict() for item in result.candidates if item.file == args.file and (not args.symbol or item.symbol == args.symbol)]
    print(json.dumps({"file": args.file, "symbol": args.symbol, "matches": matches, "warnings": list(result.warnings)}, ensure_ascii=False, indent=2))
    return 0 if matches else 1
