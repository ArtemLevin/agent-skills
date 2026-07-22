from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import AgentCapabilities

MODEL_ROUTING_SKILL = """---
name: model-routing
description: >
  Use when configuring, explaining, testing, or diagnosing phase-aware
  model routes and bounded OpenAI fallbacks in AgentKit.
---

# Purpose

Choose an executor per workflow phase while preserving the local mutation
boundary, usage accounting, and fallback limits.

# Inputs

- `.agent/agentkit.toml` model targets and routes
- task mode and optional route override
- model route, attempt, prompt-prefix, and usage artifacts

# Workflow

1. Inspect model diagnostics and configured targets.
2. Explain the target selected for every phase.
3. Confirm that implementation and targeted-fix phases use a local CLI.
4. Verify retry and fallback counts from persisted attempts.
5. Compare measured usage and accepted-task quality before changing defaults.

# Decision rules

- Direct OpenAI execution is read-only.
- Never store API-key values in configuration or artifacts.
- Schema-invalid output is a failed call.
- Never retry or switch providers after a mutating call fails.
- Live provider tests require explicit opt-in.

# Output

Return phase targets, capability constraints, fallback bounds, measured usage,
and configuration errors.

# Stop conditions

Stop when all phase targets are valid, mutating phases remain local, and the
route is reproducible from configuration.
"""


def _capabilities_schema() -> dict[str, Any]:
    defaults = AgentCapabilities().to_dict()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.local/schemas/agent-capabilities.schema.json",
        "x-agentkit-schema-version": 1,
        "title": "Agent execution capabilities",
        "type": "object",
        "additionalProperties": False,
        "required": list(defaults),
        "properties": {
            **{name: {"type": "boolean"} for name in defaults if name != "max_context_tokens"},
            "max_context_tokens": {"type": ["integer", "null"], "minimum": 1},
        },
    }


def _model_route_schema() -> dict[str, Any]:
    phase = {
        "type": "object",
        "additionalProperties": False,
        "required": ["phase", "target", "provider", "model", "reasons", "fallbacks"],
        "properties": {
            "phase": {"enum": ["plan", "implementation", "review", "targeted_fix"]},
            "target": {"type": "string", "minLength": 1},
            "provider": {"enum": ["cli", "openai"]},
            "model": {"type": "string"},
            "reasons": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "fallbacks": {"type": "array", "items": {"type": "string"}},
        },
    }
    phases = ("plan", "implementation", "review", "targeted_fix")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.local/schemas/model-route.schema.json",
        "title": "AgentKit phase model route",
        "type": "object",
        "additionalProperties": False,
        "required": ["version", "route", "phases", "warnings"],
        "properties": {
            "version": {"const": 1},
            "route": {"type": "string", "minLength": 1},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "phases": {
                "type": "object",
                "required": list(phases),
                "additionalProperties": False,
                "properties": {name: {"$ref": "#/$defs/phase"} for name in phases},
            },
        },
        "$defs": {"phase": phase},
    }


def _attempts_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.local/schemas/model-attempts.schema.json",
        "title": "AgentKit model execution attempts",
        "type": "object",
        "additionalProperties": False,
        "required": ["version", "attempts"],
        "properties": {
            "version": {"const": 1},
            "attempts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "phase", "target", "provider", "model", "attempt", "kind",
                        "returncode", "passed", "duration_seconds", "usage",
                    ],
                    "properties": {
                        "phase": {"enum": ["plan", "implementation", "review", "targeted_fix"]},
                        "target": {"type": "string", "minLength": 1},
                        "provider": {"enum": ["cli", "openai"]},
                        "model": {"type": "string"},
                        "attempt": {"type": "integer", "minimum": 1},
                        "kind": {"enum": ["primary", "retry", "fallback"]},
                        "returncode": {"type": ["integer", "null"]},
                        "passed": {"type": "boolean"},
                        "duration_seconds": {"type": "number", "minimum": 0},
                        "usage": {"type": ["object", "null"]},
                    },
                },
            },
        },
    }


def _prompt_prefix_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.local/schemas/prompt-prefix.schema.json",
        "title": "AgentKit stable prompt prefix metadata",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "version", "stable_prefix_hash", "stable_prefix_chars", "dynamic_context_chars",
            "phase", "target", "provider", "model",
        ],
        "properties": {
            "version": {"const": 1},
            "stable_prefix_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            "stable_prefix_chars": {"type": "integer", "minimum": 0},
            "dynamic_context_chars": {"type": "integer", "minimum": 0},
            "phase": {"enum": ["plan", "implementation", "review", "targeted_fix"]},
            "target": {"type": "string", "minLength": 1},
            "provider": {"enum": ["cli", "openai"]},
            "model": {"type": "string"},
        },
    }


def ensure_model_runtime_files(project_root: Path) -> dict[str, str]:
    skill = project_root / ".agent/skills/model-routing/SKILL.md"
    if not skill.is_file():
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(MODEL_ROUTING_SKILL, encoding="utf-8")

    schema_dir = project_root / ".agent/schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schemas = {
        "agent-capabilities.schema.json": _capabilities_schema(),
        "model-route.schema.json": _model_route_schema(),
        "model-attempts.schema.json": _attempts_schema(),
        "prompt-prefix.schema.json": _prompt_prefix_schema(),
    }
    paths: dict[str, str] = {"skill": str(skill)}
    for name, payload in schemas.items():
        path = schema_dir / name
        if not path.is_file():
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        paths[name] = str(path)
    return paths
