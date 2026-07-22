#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

try:
    from jsonschema.validators import Draft202012Validator
except ImportError:  # Optional in the minimal platform matrix.
    Draft202012Validator = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentkit.contracts import (  # noqa: E402
    ARTIFACT_SCHEMAS,
    PACKAGE_VERSION,
    STABLE_MAKE_TARGETS,
)


def main() -> int:
    errors: list[str] = []
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packaged = str(project["project"]["version"])
    if packaged != PACKAGE_VERSION:
        errors.append(f"pyproject version {packaged} != runtime version {PACKAGE_VERSION}")

    schema_names = tuple(sorted(path.name for path in (ROOT / "schemas").glob("*.json")))
    if schema_names != tuple(sorted(ARTIFACT_SCHEMAS)):
        errors.append("schema registry does not match schemas/ contents")
    for name in schema_names:
        try:
            payload = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: invalid JSON: {exc}")
            continue
        properties = payload.get("properties", {})
        versioned = (
            payload.get("x-agentkit-schema-version") == 1
            or properties.get("version", {}).get("const") == 1
        )
        if not versioned:
            errors.append(f"{name}: no AgentKit schema version")
        if Draft202012Validator is not None:
            try:
                Draft202012Validator.check_schema(payload)
            except Exception as exc:  # jsonschema exposes several schema exceptions.
                errors.append(f"{name}: invalid Draft 2020-12 schema: {exc}")

    makefile = (ROOT / "src/agentkit/init_project.py").read_text(encoding="utf-8")
    for target in STABLE_MAKE_TARGETS:
        if f"{target}:" not in makefile:
            errors.append(f"missing Make target: {target}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(
        f"release contracts valid: version={PACKAGE_VERSION}, "
        f"schemas={len(schema_names)}, make_targets={len(STABLE_MAKE_TARGETS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
