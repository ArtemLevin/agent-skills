from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path

from agentkit.config import configured_project_root, load_config
from agentkit.models import RunMode
from agentkit.triage import classify_task

from .config import load_model_runtime_config
from .openai import OpenAIResponsesAdapter
from .router import build_route_plan, target_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentkit models")
    parser.add_argument("--project-root")
    sub = parser.add_subparsers(dest="models_command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("list")
    route = sub.add_parser("route")
    route.add_argument("--task", required=True)
    route.add_argument("--phase", choices=["plan", "implementation", "review", "targeted_fix"])
    route.add_argument("--mode", choices=[item.value for item in RunMode], default="auto")
    route.add_argument("--route")
    route.add_argument("--explain", action="store_true")
    return parser


def build_provider_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentkit providers")
    parser.add_argument("--project-root")
    sub = parser.add_subparsers(dest="providers_command", required=True)
    sub.add_parser("list")
    test = sub.add_parser("test")
    test.add_argument("provider", choices=["openai"])
    test.add_argument("--target")
    test.add_argument("--live", action="store_true")
    return parser


def _doctor(config: object) -> dict[str, object]:
    targets = [target for target in config.targets.values() if target.provider == "openai"]
    sdk = importlib.util.find_spec("openai") is not None
    return {
        "enabled": config.enabled,
        "openai_sdk_installed": sdk,
        "targets": [
            {
                **target_summary(target),
                "api_key_env": target.api_key_env,
                "api_key_available": bool(os.environ.get(target.api_key_env)),
                "store": target.store,
            }
            for target in targets
        ],
        "paid_request_performed": False,
    }


def models_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = configured_project_root(args.project_root)
    core = load_config(root)
    config = load_model_runtime_config(root, core.agent)
    if args.models_command == "doctor":
        print(json.dumps(_doctor(config), ensure_ascii=False, indent=2))
        return 0
    if args.models_command == "list":
        payload = {
            "enabled": config.enabled,
            "default_route": config.default_route,
            "targets": [target_summary(item) for item in config.targets.values()],
            "routes": config.routes,
            "fallback": {key: list(value) for key, value in config.fallbacks.items()},
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    triage = classify_task(args.task, RunMode(args.mode))
    plan = build_route_plan(config, mode=triage.mode, route_override=args.route)
    payload = plan.to_dict()
    if args.phase:
        payload["phases"] = {args.phase: payload["phases"][args.phase]}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def providers_main(argv: list[str] | None = None) -> int:
    args = build_provider_parser().parse_args(argv)
    root = configured_project_root(args.project_root)
    core = load_config(root)
    config = load_model_runtime_config(root, core.agent)
    if args.providers_command == "list":
        print(
            json.dumps(
                {
                    "supported_providers": ["cli", "openai"],
                    "targets": [target_summary(item) for item in config.targets.values()],
                    "openai": _doctor(config),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    candidates = [target for target in config.targets.values() if target.provider == args.provider]
    if args.target:
        candidates = [target for target in candidates if target.name == args.target]
    if not candidates:
        raise ValueError("No matching OpenAI target is configured")
    target = candidates[0]
    if not args.live:
        payload = _doctor(config)
        payload["selected_target"] = target.name
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    result = OpenAIResponsesAdapter(target).execute(
        "Return exactly the word OK.",
        phase="plan",
        cwd=Path(root),
    )
    print(
        json.dumps(
            {
                "target": target.name,
                "provider": target.provider,
                "model": target.model,
                "passed": result.passed,
                "returncode": result.returncode,
                "error": result.stderr,
                "usage": result.usage.to_dict() if result.usage else None,
                "paid_request_performed": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.passed else result.returncode or 2
