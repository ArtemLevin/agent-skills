# ruff: noqa: E501
from __future__ import annotations

from pathlib import Path

from .config import ensure_quality_config


MAKEFILE_QUALITY = r'''

# BEGIN AGENTKIT QUALITY
QUALITY_RUN_ID ?= latest

.PHONY: ai-quality-doctor ai-quality ai-quality-details ai-quality-hotspots ai-quality-show

ai-quality-doctor:
	$(AGENTKIT) quality doctor

ai-quality:
	$(AGENTKIT) quality analyze

ai-quality-details:
	$(AGENTKIT) quality analyze --details

ai-quality-hotspots:
	$(AGENTKIT) quality hotspots --run-id "$(QUALITY_RUN_ID)"

ai-quality-show:
	$(AGENTKIT) quality show --run-id "$(QUALITY_RUN_ID)"
# END AGENTKIT QUALITY
'''

QUALITY_SKILL = '''---
name: quality-diagnostics
description: >
  Use when collecting or interpreting bounded code-health evidence from a configured quality provider without treating metrics as proof of a defect.
---

# Purpose

Collect deterministic, machine-readable maintainability evidence, identify bounded hotspots, and explain availability or uncertainty without changing completion semantics.

# Inputs

- `.agent/agentkit.toml` quality configuration
- `quality-provider.json`
- `quality-before.json`
- `quality-hotspots.json`
- relevant source code for any hotspot being interpreted

# Workflow

1. Check provider availability and supported language.
2. Reuse a valid content-addressed snapshot when available.
3. Run project-level analysis first unless details are explicitly required.
4. Escalate to bounded detail only when configured or when project status is elevated.
5. Read source code before converting a metric hotspot into a concrete recommendation.
6. Report provider limits, truncation, and missing fields explicitly.

# Decision rules

- Quality metrics are navigation and risk evidence, not proof that behavior is wrong.
- Never replace a missing metric with zero.
- Never place the complete raw provider report into an agent prompt.
- Prefer source code and executed tests over static quality inference.
- In report mode, findings do not block completion.
- Keep hotspot lists bounded by configuration.

# Output

Return availability, compact project metrics, bounded hotspots, artifact paths, warnings, and the smallest evidence-backed next action.

# Stop conditions

Stop when the snapshot is current, bounded, schema-valid, and every unavailable or partial field is explicit.
'''

QUALITY_SNAPSHOT_SCHEMA = r'''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/quality-snapshot.schema.json",
  "title": "AgentKit quality snapshot",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "generated_at", "availability", "provider", "provider_version", "source_fingerprint", "project", "statistics", "hotspots", "warnings", "truncated", "cache_hit", "details"],
  "properties": {
    "version": {"const": 1},
    "generated_at": {"type": "string"},
    "availability": {"enum": ["available", "unavailable", "unsupported", "failed", "partial"]},
    "provider": {"type": "string"},
    "provider_version": {"type": "string"},
    "source_fingerprint": {"type": "string"},
    "project": {
      "type": ["object", "null"],
      "additionalProperties": false,
      "required": ["score", "refactoring_pressure", "overengineering_pressure", "complexity_density", "status", "language", "loc"],
      "properties": {
        "score": {"type": ["number", "null"]},
        "refactoring_pressure": {"type": ["number", "null"]},
        "overengineering_pressure": {"type": ["number", "null"]},
        "complexity_density": {"type": ["number", "null"]},
        "status": {"type": "string"},
        "language": {"type": "string"},
        "loc": {"type": ["integer", "null"]}
      }
    },
    "statistics": {"type": "object", "additionalProperties": {"$ref": "#/$defs/stat"}},
    "hotspots": {"type": "array", "items": {"$ref": "#/$defs/hotspot"}},
    "warnings": {"type": "array", "items": {"type": "string"}},
    "truncated": {"type": "boolean"},
    "cache_hit": {"type": "boolean"},
    "details": {"type": "boolean"}
  },
  "$defs": {
    "stat": {
      "type": "object",
      "additionalProperties": false,
      "required": ["avg", "min", "max", "p50", "p90"],
      "properties": {
        "avg": {"type": ["number", "null"]},
        "min": {"type": ["number", "null"]},
        "max": {"type": ["number", "null"]},
        "p50": {"type": ["number", "null"]},
        "p90": {"type": ["number", "null"]}
      }
    },
    "hotspot": {
      "type": "object",
      "additionalProperties": false,
      "required": ["kind", "name", "file", "class_name", "status", "status_score", "loc", "complexity", "complexity_total", "complexity_density", "refactoring_pressure", "overengineering_pressure", "reasons", "rank_score"],
      "properties": {
        "kind": {"enum": ["package", "module", "class", "method", "function"]},
        "name": {"type": "string"},
        "file": {"type": "string"},
        "class_name": {"type": "string"},
        "status": {"type": "string"},
        "status_score": {"type": ["number", "null"]},
        "loc": {"type": ["integer", "null"]},
        "complexity": {"type": ["number", "null"]},
        "complexity_total": {"type": ["number", "null"]},
        "complexity_density": {"type": ["number", "null"]},
        "refactoring_pressure": {"type": ["number", "null"]},
        "overengineering_pressure": {"type": ["number", "null"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "rank_score": {"type": "number"}
      }
    }
  }
}'''

QUALITY_HOTSPOTS_SCHEMA = r'''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/quality-hotspots.schema.json",
  "title": "AgentKit quality hotspots",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "generated_at", "availability", "provider", "provider_version", "source_fingerprint", "hotspots", "warnings", "truncated"],
  "properties": {
    "version": {"const": 1},
    "generated_at": {"type": "string"},
    "availability": {"enum": ["available", "unavailable", "unsupported", "failed", "partial"]},
    "provider": {"type": "string"},
    "provider_version": {"type": "string"},
    "source_fingerprint": {"type": "string"},
    "hotspots": {"type": "array", "items": {"type": "object"}},
    "warnings": {"type": "array", "items": {"type": "string"}},
    "truncated": {"type": "boolean"}
  }
}'''

QUALITY_PROVIDER_SCHEMA = r'''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/quality-provider.schema.json",
  "title": "AgentKit quality provider status",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "availability", "provider", "provider_version", "executable", "detected_languages", "supported_languages", "message", "capabilities"],
  "properties": {
    "version": {"const": 1},
    "availability": {"enum": ["available", "unavailable", "unsupported", "failed", "partial"]},
    "provider": {"type": "string"},
    "provider_version": {"type": "string"},
    "executable": {"type": "string"},
    "detected_languages": {"type": "array", "items": {"type": "string"}},
    "supported_languages": {"type": "array", "items": {"type": "string"}},
    "message": {"type": "string"},
    "capabilities": {"type": ["object", "null"]}
  }
}'''


def _append_once(path: Path, block: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker not in text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + block, encoding="utf-8")


def ensure_quality_project_files(project_root: Path) -> dict[str, str]:
    config = ensure_quality_config(project_root)
    makefile = project_root / ".agent" / "Makefile.agent"
    _append_once(makefile, MAKEFILE_QUALITY, "# BEGIN AGENTKIT QUALITY")

    skill = project_root / ".agent" / "skills" / "quality-diagnostics" / "SKILL.md"
    if not skill.is_file():
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(QUALITY_SKILL, encoding="utf-8")

    schema_dir = project_root / ".agent" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schemas = {
        "quality-snapshot.schema.json": QUALITY_SNAPSHOT_SCHEMA,
        "quality-hotspots.schema.json": QUALITY_HOTSPOTS_SCHEMA,
        "quality-provider.schema.json": QUALITY_PROVIDER_SCHEMA,
    }
    for name, content in schemas.items():
        path = schema_dir / name
        if not path.is_file():
            path.write_text(content + "\n", encoding="utf-8")
    return {
        "config": str(config),
        "makefile": str(makefile),
        "skill": str(skill),
        "schema_dir": str(schema_dir),
    }
