from __future__ import annotations

from pathlib import Path

from .ci_config import QualityCIConfig, ensure_quality_ci_config
from .ci_workflow import render_quality_workflow

MAKEFILE_CI = r'''

# BEGIN AGENTKIT QUALITY CI
QUALITY_CI_BASE_REF ?= main
QUALITY_CI_RUN_ID ?=
QUALITY_CI_SUMMARY_RUN_ID ?= latest
QUALITY_CI_FORCE ?=

.PHONY: ai-quality-ci-install ai-quality-ci-preview ai-quality-ci-validate ai-quality-ci ai-quality-ci-summary

ai-quality-ci-install:
	$(AGENTKIT) ci quality install $(if $(QUALITY_CI_FORCE),--force,)

ai-quality-ci-preview:
	$(AGENTKIT) ci quality preview

ai-quality-ci-validate:
	$(AGENTKIT) ci quality validate

ai-quality-ci:
	$(AGENTKIT) ci quality run-local --base-ref "$(QUALITY_CI_BASE_REF)" $(if $(QUALITY_CI_RUN_ID),--run-id "$(QUALITY_CI_RUN_ID)",)

ai-quality-ci-summary:
	$(AGENTKIT) ci quality summary --run-id "$(QUALITY_CI_SUMMARY_RUN_ID)"
# END AGENTKIT QUALITY CI
'''

SKILL = '''---
name: quality-ci
description: >
  Use when installing, previewing, or interpreting the read-only AgentKit quality workflow for pull requests and local merge-base checks.
---

# Purpose

Run the same provider-neutral quality lifecycle locally and in GitHub Actions, publish bounded evidence, and preserve gate exit semantics.

# Inputs

- full Git history and a resolvable base ref;
- `.agent/agentkit.toml` quality and quality.ci configuration;
- configured quality provider;
- native quality baseline, current, diff, and gate artifacts.

# Workflow

1. Confirm the clone is not shallow.
2. Resolve the configured base ref and merge-base.
3. Analyze the baseline in a detached temporary worktree.
4. Analyze the current worktree through the provider abstraction.
5. Compare snapshots and apply the existing quality gate.
6. Write bounded Markdown summary and downloadable artifacts.
7. Return the original quality exit code after summary and upload steps.

# Decision rules

- Never use the pull-request head as its own clean baseline.
- Never hard-code a provider command in the workflow.
- Keep default GitHub permissions read-only.
- Do not overwrite a user-modified workflow without explicit `--force`.
- Always upload evidence after a gate failure.
- Missing or non-comparable measurements remain explicit.

# Output

Return the run id, resolved merge-base, gate result, exit code, summary path, artifact directory, and warnings.

# Stop conditions

Stop after artifacts and summary are durable and the configured gate exit code is preserved.
'''

SCHEMA = '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/quality-ci-result.schema.json",
  "title": "AgentKit quality CI result",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "version", "run_id", "status", "base_ref", "merge_base",
    "gate_allowed", "exit_code", "run_directory",
    "artifact_directory", "summary_path", "warnings"
  ],
  "properties": {
    "version": {"const": 1},
    "run_id": {"type": "string", "minLength": 1},
    "status": {"enum": ["passed", "failed", "error"]},
    "base_ref": {"type": "string"},
    "merge_base": {"type": "string"},
    "gate_allowed": {"type": "boolean"},
    "exit_code": {"enum": [0, 2, 6]},
    "run_directory": {"type": "string"},
    "artifact_directory": {"type": "string"},
    "summary_path": {"type": "string"},
    "warnings": {"type": "array", "items": {"type": "string"}}
  }
}'''


def _append_once(path: Path, content: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker not in text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + content, encoding="utf-8")


def ensure_quality_ci_files(project_root: Path) -> dict[str, str]:
    config = ensure_quality_ci_config(project_root)
    makefile = project_root / ".agent" / "Makefile.agent"
    _append_once(makefile, MAKEFILE_CI, "# BEGIN AGENTKIT QUALITY CI")

    skill = project_root / ".agent" / "skills" / "quality-ci" / "SKILL.md"
    if not skill.is_file():
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(SKILL, encoding="utf-8")

    schema = project_root / ".agent" / "schemas" / "quality-ci-result.schema.json"
    if not schema.is_file():
        schema.parent.mkdir(parents=True, exist_ok=True)
        schema.write_text(SCHEMA + "\n", encoding="utf-8")

    template = project_root / ".agent" / "templates" / "agentkit-quality.yml"
    if not template.is_file():
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_text(
            render_quality_workflow(QualityCIConfig()),
            encoding="utf-8",
        )
    return {
        "config": str(config),
        "makefile": str(makefile),
        "skill": str(skill),
        "schema": str(schema),
        "template": str(template),
    }
