from __future__ import annotations

from pathlib import Path

from .config import ensure_evaluation_config

MAKEFILE_EVALS = r'''

# BEGIN AGENTKIT EVALUATIONS
EVAL_TASK ?=
EVAL_DIR ?= evals/tasks
EVAL_RUNS ?=
EVAL_BASELINE ?=
EVAL_CURRENT ?=
EVAL_OUTPUT ?=
EVAL_SMOKE ?=
REPORT_LIMIT ?= 50

.PHONY: ai-eval ai-eval-suite ai-eval-compare ai-quality-report ai-quality-trend ai-quality-regressions ai-quality-efficiency

ai-eval:
	$(AGENTKIT) eval run "$(EVAL_TASK)" $(if $(EVAL_RUNS),--runs "$(EVAL_RUNS)",)

ai-eval-suite:
	$(AGENTKIT) eval suite "$(EVAL_DIR)" $(if $(EVAL_RUNS),--runs "$(EVAL_RUNS)",) $(if $(EVAL_SMOKE),--smoke,)

ai-eval-compare:
	$(AGENTKIT) eval compare "$(EVAL_BASELINE)" "$(EVAL_CURRENT)" $(if $(EVAL_OUTPUT),--output "$(EVAL_OUTPUT)",)

ai-quality-report:
	$(AGENTKIT) quality report --limit "$(REPORT_LIMIT)"

ai-quality-trend:
	$(AGENTKIT) quality trend --limit "$(REPORT_LIMIT)"

ai-quality-regressions:
	$(AGENTKIT) quality regressions --limit "$(REPORT_LIMIT)"

ai-quality-efficiency:
	$(AGENTKIT) efficiency report --limit "$(REPORT_LIMIT)"
# END AGENTKIT EVALUATIONS
'''

SKILL = '''---
name: evaluation-harness
description: >
  Use when measuring AgentKit engineering outcomes across deterministic fixture tasks, repeated runs, configuration variants, and historical comparisons.
---

# Purpose

Evaluate correctness, efficiency, and quality as separate evidence dimensions so optimization claims cannot hide failed acceptance checks or readiness regressions.

# Inputs

- committed evaluation manifest;
- deterministic fixture repository;
- AgentKit configuration and experiment dimensions;
- acceptance commands and file constraints;
- optional quality and budget expectations;
- one or more completed evaluation summaries for comparison.

# Workflow

1. Validate the manifest and reject secret-like experiment fields.
2. Hash the source fixture and copy it into an isolated workspace.
3. Initialize a deterministic Git baseline inside the copy.
4. Run AgentKit and execute explicit acceptance commands.
5. Collect completion, review, scope, usage, context, and quality evidence.
6. Verify that the source fixture remained unchanged.
7. Aggregate repeated runs without converting unknown usage into zero.
8. Compare compatible summaries with explicit regression thresholds.
9. Persist JSON and bounded Markdown reports.

# Decision rules

- Correctness regressions dominate efficiency improvements.
- Token averages include measured runs only and report unknown calls separately.
- Quality metrics remain unavailable when evidence is absent.
- Threshold equality passes; only strict exceedance is a regression.
- Never publish secret values, environment dumps, or full unbounded command output.
- Full provider-cost suites are opt-in; smoke suites use manifests marked `smoke: true`.

# Output

Return immutable manifest evidence, per-run results, dimension-separated summary metrics, explicit warnings, and comparison regressions or improvements.

# Stop conditions

Stop when fixture preservation is proven, acceptance evidence is durable, unknown measurements are explicit, and no conclusion relies on a single opaque composite score.
'''

EVAL_TASK_SCHEMA = '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/eval-task.schema.json",
  "title": "AgentKit evaluation task",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "repository_fixture", "mode", "task", "acceptance"],
  "properties": {
    "version": {"const": 1},
    "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._-]{2,127}$"},
    "repository_fixture": {"type": "string", "minLength": 1},
    "mode": {"enum": ["fast", "standard", "deep"]},
    "task": {"type": "string", "minLength": 1},
    "repetitions": {"type": "integer", "minimum": 1},
    "smoke": {"type": "boolean"},
    "integration": {"type": "boolean"},
    "human_accepted": {"type": ["boolean", "null"]},
    "acceptance": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "commands": {"type": "array", "items": {"type": "array", "minItems": 1, "items": {"type": "string"}}},
        "required_files": {"type": "array", "items": {"type": "string"}},
        "forbidden_files": {"type": "array", "items": {"type": "string"}}
      }
    },
    "quality": {"type": "object"},
    "budget": {"type": "object"},
    "experiment": {"type": "object"}
  }
}'''

EVAL_RUN_SCHEMA = '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/eval-run.schema.json",
  "title": "AgentKit evaluation run result",
  "type": "object",
  "required": ["version", "evaluation_id", "task_id", "run_id", "status", "correctness", "efficiency", "quality", "fixture_preserved"],
  "properties": {
    "version": {"const": 1},
    "status": {"enum": ["passed", "failed", "error"]},
    "correctness": {"type": "object"},
    "efficiency": {"type": "object"},
    "quality": {"type": "object"},
    "fixture_preserved": {"type": "boolean"}
  }
}'''

EVAL_SUMMARY_SCHEMA = '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/eval-summary.schema.json",
  "title": "AgentKit evaluation summary",
  "type": "object",
  "required": ["version", "evaluation_id", "task_ids", "kind", "run_count", "correctness", "efficiency", "quality"],
  "properties": {
    "version": {"const": 1},
    "kind": {"enum": ["task", "suite"]},
    "correctness": {"type": "object"},
    "efficiency": {"type": "object"},
    "quality": {"type": "object"}
  }
}'''

EVAL_COMPARISON_SCHEMA = '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/eval-comparison.schema.json",
  "title": "AgentKit evaluation comparison",
  "type": "object",
  "required": ["version", "baseline", "current", "compatible", "verdict", "correctness", "efficiency", "quality", "regressions", "improvements"],
  "properties": {
    "version": {"const": 1},
    "verdict": {"enum": ["regression", "improved", "neutral", "incomparable"]},
    "regressions": {"type": "array", "items": {"type": "string"}},
    "improvements": {"type": "array", "items": {"type": "string"}}
  }
}'''

TEMPLATE = '''version: 1
id: python-local-bugfix-001
repository_fixture: evals/fixtures/python_service
mode: standard
task: Fix duplicate retry scheduling without changing the public API.
repetitions: 1
smoke: true
acceptance:
  commands:
    - [python, -m, unittest, discover, -s, tests, -v]
  required_files:
    - tests/test_retry.py
  forbidden_files:
    - pyproject.toml
quality:
  allow_new_critical_hotspots: 0
budget:
  max_agent_calls: 4
experiment:
  graphify: true
  context_cache: true
  quality_context: true
'''


def _append_once(path: Path, content: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker not in text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + content, encoding="utf-8")


def ensure_evaluation_files(project_root: Path) -> dict[str, str]:
    config = ensure_evaluation_config(project_root)
    makefile = project_root / ".agent" / "Makefile.agent"
    _append_once(makefile, MAKEFILE_EVALS, "# BEGIN AGENTKIT EVALUATIONS")

    skill = project_root / ".agent" / "skills" / "evaluation-harness" / "SKILL.md"
    if not skill.is_file():
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(SKILL, encoding="utf-8")

    schemas = {
        "eval-task.schema.json": EVAL_TASK_SCHEMA,
        "eval-run.schema.json": EVAL_RUN_SCHEMA,
        "eval-summary.schema.json": EVAL_SUMMARY_SCHEMA,
        "eval-comparison.schema.json": EVAL_COMPARISON_SCHEMA,
    }
    for name, content in schemas.items():
        path = project_root / ".agent" / "schemas" / name
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content + "\n", encoding="utf-8")

    template = project_root / ".agent" / "templates" / "eval-task.yaml"
    if not template.is_file():
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_text(TEMPLATE, encoding="utf-8")

    return {
        "config": str(config),
        "makefile": str(makefile),
        "skill": str(skill),
        "template": str(template),
        "schemas": str(project_root / ".agent" / "schemas"),
    }
