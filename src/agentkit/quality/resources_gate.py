# ruff: noqa: E501
from __future__ import annotations

from pathlib import Path


MAKEFILE_QUALITY_GATE = r'''

# BEGIN AGENTKIT QUALITY GATE
QUALITY_BASE_BRANCH ?= main

.PHONY: ai-quality-baseline ai-quality-after ai-quality-compare ai-quality-gate ai-quality-cycle

ai-quality-baseline:
	$(AGENTKIT) quality baseline

ai-quality-after:
	$(AGENTKIT) quality analyze --stage after

ai-quality-compare:
	$(AGENTKIT) quality compare --run-id "$(QUALITY_RUN_ID)"

ai-quality-gate:
	$(AGENTKIT) quality gate --run-id "$(QUALITY_RUN_ID)"

ai-quality-cycle:
	$(AGENTKIT) quality cycle
# END AGENTKIT QUALITY GATE
'''

QUALITY_GATE_SKILL = '''---
name: quality-regression-gate
description: >
  Use when comparing quality snapshots, evaluating absolute or delta thresholds, and deciding whether a maintainability regression should report, warn, or block completion.
---

# Purpose

Compare schema-valid quality evidence without treating missing measurements as improvement, then apply explicit report, warn, or enforce policy.

# Inputs

- `quality-before.json`
- `quality-after.json`
- `quality-diff.json`
- `[quality]`, `[quality.absolute]`, and `[quality.delta]`
- source code and executed tests for interpretation

# Workflow

1. Verify provider, version, language, and configuration comparability.
2. Compute directional project metric deltas.
3. Classify new, resolved, persisting, and changed hotspots.
4. Evaluate only configured absolute and delta thresholds.
5. Apply unavailable-data policy explicitly.
6. Write `quality-gate.json` and update completion evidence.
7. Keep report and warn modes non-blocking.

# Decision rules

- Never treat a missing value as zero or as an improvement.
- Higher score, RP, OP, and density are treated as worse by the current gate.
- Threshold equality passes; only a strict exceedance violates.
- Source code and tests outrank static quality metrics.
- Merge-base analysis must use a temporary worktree and never replace the user worktree.
- Enforce mode blocks only configured violations or unavailable_policy=stop.

# Output

Return metric, baseline, current, delta, threshold, scope, comparability warnings, gate mode, and whether completion is allowed.

# Stop conditions

Stop when the final post-fix snapshot is compared once, every missing measurement is explicit, and the gate artifact is reproducible.
'''

QUALITY_DIFF_SCHEMA = r'''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/quality-diff.schema.json",
  "title": "AgentKit quality diff",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "generated_at", "provider", "provider_version", "baseline_fingerprint", "current_fingerprint", "comparable", "metrics", "new_hotspots", "resolved_hotspots", "persisting_hotspots", "changed_hotspots", "warnings"],
  "properties": {
    "version": {"const": 1},
    "generated_at": {"type": "string"},
    "provider": {"type": "string"},
    "provider_version": {"type": "string"},
    "baseline_fingerprint": {"type": "string"},
    "current_fingerprint": {"type": "string"},
    "comparable": {"type": "boolean"},
    "metrics": {"type": "object", "additionalProperties": {"type": "object"}},
    "new_hotspots": {"type": "array", "items": {"type": "object"}},
    "resolved_hotspots": {"type": "array", "items": {"type": "object"}},
    "persisting_hotspots": {"type": "array", "items": {"type": "object"}},
    "changed_hotspots": {"type": "array", "items": {"type": "object"}},
    "warnings": {"type": "array", "items": {"type": "string"}}
  }
}'''

QUALITY_GATE_SCHEMA = r'''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/quality-gate.schema.json",
  "title": "AgentKit quality gate",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "generated_at", "mode", "unavailable_policy", "available", "comparable", "passed", "allowed", "violations", "warnings"],
  "properties": {
    "version": {"const": 1},
    "generated_at": {"type": "string"},
    "mode": {"enum": ["report", "warn", "enforce"]},
    "unavailable_policy": {"enum": ["allow", "warn", "stop"]},
    "available": {"type": "boolean"},
    "comparable": {"type": "boolean"},
    "passed": {"type": "boolean"},
    "allowed": {"type": "boolean"},
    "violations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["kind", "metric", "threshold", "baseline", "current", "delta", "scope", "message"]
      }
    },
    "warnings": {"type": "array", "items": {"type": "string"}}
  }
}'''


def _append_once(path: Path, block: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker not in text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + block, encoding="utf-8")


def ensure_quality_gate_project_files(project_root: Path) -> dict[str, str]:
    makefile = project_root / ".agent" / "Makefile.agent"
    _append_once(makefile, MAKEFILE_QUALITY_GATE, "# BEGIN AGENTKIT QUALITY GATE")

    skill = project_root / ".agent" / "skills" / "quality-regression-gate" / "SKILL.md"
    if not skill.is_file():
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(QUALITY_GATE_SKILL, encoding="utf-8")

    schema_dir = project_root / ".agent" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schemas = {
        "quality-diff.schema.json": QUALITY_DIFF_SCHEMA,
        "quality-gate.schema.json": QUALITY_GATE_SCHEMA,
    }
    for name, content in schemas.items():
        path = schema_dir / name
        if not path.is_file():
            path.write_text(content + "\n", encoding="utf-8")
    return {"makefile": str(makefile), "skill": str(skill), "schema_dir": str(schema_dir)}
