from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _schema(title: str, required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": title,
        "type": "object",
        "required": required,
        "properties": properties,
    }


RELEASE_SCHEMAS: dict[str, dict[str, Any]] = {
    "installation-manifest.schema.json": _schema(
        "AgentKit installation manifest",
        ["version", "agentkit_version", "previous_version", "installed_at", "resources"],
        {
            "version": {"const": 1},
            "agentkit_version": {"type": "string"},
            "previous_version": {"type": "string"},
            "installed_at": {"type": "string"},
            "resources": {"type": "array", "items": {"type": "object"}},
        },
    ),
    "migration-report.schema.json": _schema(
        "AgentKit migration report",
        ["version", "installed_version", "target_version", "compatible", "actions"],
        {
            "version": {"const": 1},
            "installed_version": {"type": "string"},
            "target_version": {"type": "string"},
            "compatible": {"type": "boolean"},
            "actions": {"type": "array", "items": {"type": "object"}},
        },
    ),
    "run-state.schema.json": _schema(
        "AgentKit run lifecycle",
        ["version", "run_id", "status", "phase", "mutation_started", "mutation_completed"],
        {
            "version": {"const": 1},
            "run_id": {"type": "string"},
            "status": {"enum": ["running", "completed", "failed", "manual_recovery_required"]},
            "phase": {"type": "string"},
            "mutation_started": {"type": "boolean"},
            "mutation_completed": {"type": "boolean"},
        },
    ),
    "self-test.schema.json": _schema(
        "AgentKit self-test result",
        ["version", "ready", "checks", "warnings"],
        {
            "version": {"const": 1},
            "ready": {"type": "boolean"},
            "checks": {"type": "array", "items": {"type": "object"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
    ),
    "diagnostics-manifest.schema.json": _schema(
        "AgentKit diagnostics bundle manifest",
        ["version", "created_at", "agentkit_version", "files", "redacted"],
        {
            "version": {"const": 1},
            "created_at": {"type": "string"},
            "agentkit_version": {"type": "string"},
            "files": {"type": "array", "items": {"type": "string"}},
            "redacted": {"const": True},
        },
    ),
}

MAKEFILE_RELEASE = r'''

# BEGIN AGENTKIT RELEASE
.PHONY: ai-upgrade-check ai-migrate ai-self-test ai-diagnostics ai-release-check

ai-upgrade-check:
	$(AGENTKIT) migrate check

ai-migrate:
	$(AGENTKIT) migrate apply

ai-self-test:
	$(AGENTKIT) self-test

ai-diagnostics:
	$(AGENTKIT) diagnostics bundle

ai-release-check: ai-upgrade-check ai-self-test
# END AGENTKIT RELEASE
'''


def ensure_release_files(project_root: Path) -> dict[str, str]:
    root = project_root / ".agent" / "schemas"
    root.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}
    for name, payload in RELEASE_SCHEMAS.items():
        path = root / name
        if not path.exists():
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        result[name] = str(path)
    makefile = project_root / ".agent" / "Makefile.agent"
    makefile_text = makefile.read_text(encoding="utf-8") if makefile.exists() else ""
    if "# BEGIN AGENTKIT RELEASE" not in makefile_text:
        makefile.parent.mkdir(parents=True, exist_ok=True)
        makefile.write_text(makefile_text.rstrip() + MAKEFILE_RELEASE, encoding="utf-8")
    result["makefile"] = str(makefile)
    return result
