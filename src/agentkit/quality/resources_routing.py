from __future__ import annotations

from pathlib import Path

from .routing_config import ensure_quality_routing_config


MAKEFILE_ROUTING = r'''

# BEGIN AGENTKIT QUALITY ROUTING
QUALITY_ROUTE_RUN_ID ?= latest
QUALITY_ROUTE_MODE ?= auto
QUALITY_ROUTE_LIMIT ?=

.PHONY: ai-quality-triage ai-quality-check ai-quality-plan ai-quality-route

ai-quality-triage:
	$(AGENTKIT) quality triage $(if $(TASK),--task "$(TASK)",) $(if $(TASK_FILE),--task-file "$(TASK_FILE)",) --mode "$(QUALITY_ROUTE_MODE)" --run-id "$(QUALITY_ROUTE_RUN_ID)" $(if $(QUALITY_ROUTE_LIMIT),--limit "$(QUALITY_ROUTE_LIMIT)",)

ai-quality-plan:
	$(AGENTKIT) quality plan-checks $(if $(TASK),--task "$(TASK)",) $(if $(TASK_FILE),--task-file "$(TASK_FILE)",) --mode "$(QUALITY_ROUTE_MODE)" --run-id "$(QUALITY_ROUTE_RUN_ID)" $(if $(QUALITY_ROUTE_LIMIT),--limit "$(QUALITY_ROUTE_LIMIT)",)

ai-quality-check: ai-quality-plan

ai-quality-route:
	$(AGENTKIT) quality explain-route --run-id "$(QUALITY_ROUTE_RUN_ID)"
# END AGENTKIT QUALITY ROUTING
'''

SKILL = '''---
name: quality-aware-routing
description: >
  Use before implementation to refine task mode, selected skills, approval needs, and verification depth from task-scoped quality evidence.
---

# Purpose

Escalate engineering controls only when bounded quality evidence is related to the requested task, while preserving every existing security and domain-risk rule.

# Inputs

- base deterministic triage;
- task-scoped hotspot context;
- quality snapshot metrics;
- Graphify evidence;
- quality routing thresholds;
- configured and discovered verification commands.

# Workflow

1. Preserve the base triage as the minimum risk level.
2. Evaluate only task-scoped quality candidates.
3. Apply threshold rules for complexity, RP, OP, fan-in, fan-out, and centrality.
4. Add skills, requirements, mode escalation, and approval flags with evidence.
5. Build `verification-plan.json` before implementation begins.
6. Persist the route and expose it in task and completion artifacts.

# Decision rules

- Quality evidence can escalate risk but never reduce the base mode.
- Project-wide poor health alone cannot trigger deep mode.
- Complexity above the characterization threshold requires a behavior-preserving test before structural rewrite.
- Combined high RP and OP in task scope is a crisis route.
- Missing quality evidence preserves existing triage and creates an uncertainty warning.
- Every selected verification command must have a reason and source evidence.

# Output

Return the original and effective mode, approval decision, selected skills, requirements, triggered rules, warnings, scoped evidence, and a reasoned verification plan.

# Stop conditions

Stop when the route is deterministic, no base safety rule was weakened, every selected check is explained, and preimplementation test requirements are visible.
'''

ROUTE_SCHEMA = '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/quality-route.schema.json",
  "title": "AgentKit quality-aware route",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "task", "original_mode", "effective_mode", "escalated", "approval_required", "scope_kind", "selected_skills", "risk_reasons", "requirements", "rules", "warnings", "source_snapshot", "scoped_candidates"],
  "properties": {
    "version": {"const": 1},
    "task": {"type": "string"},
    "original_mode": {"enum": ["auto", "fast", "standard", "deep"]},
    "effective_mode": {"enum": ["auto", "fast", "standard", "deep"]},
    "escalated": {"type": "boolean"},
    "approval_required": {"type": "boolean"},
    "scope_kind": {"enum": ["unknown", "healthy", "local", "systemic"]},
    "selected_skills": {"type": "array", "items": {"type": "string"}},
    "risk_reasons": {"type": "array", "items": {"type": "string"}},
    "requirements": {"type": "array", "items": {"type": "string"}},
    "rules": {"type": "array", "items": {"type": "object"}},
    "warnings": {"type": "array", "items": {"type": "string"}},
    "source_snapshot": {"type": "string"},
    "scoped_candidates": {"type": "array", "items": {"type": "object"}}
  }
}'''

PLAN_SCHEMA = '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/verification-plan.schema.json",
  "title": "AgentKit verification plan",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "selected_commands", "requirements", "escalation_conditions", "omitted_checks", "warnings"],
  "properties": {
    "version": {"const": 1},
    "selected_commands": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["command", "reason", "source_evidence", "scope", "required"]
      }
    },
    "requirements": {"type": "array", "items": {"type": "string"}},
    "escalation_conditions": {"type": "array", "items": {"type": "string"}},
    "omitted_checks": {"type": "array", "items": {"type": "string"}},
    "warnings": {"type": "array", "items": {"type": "string"}}
  }
}'''


def _append_once(path: Path, content: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker not in text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + content, encoding="utf-8")


def ensure_quality_routing_files(project_root: Path) -> dict[str, str]:
    ensure_quality_routing_config(project_root)
    makefile = project_root / ".agent" / "Makefile.agent"
    _append_once(makefile, MAKEFILE_ROUTING, "# BEGIN AGENTKIT QUALITY ROUTING")
    skill = project_root / ".agent" / "skills" / "quality-aware-routing" / "SKILL.md"
    if not skill.is_file():
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(SKILL, encoding="utf-8")
    route_schema = project_root / ".agent" / "schemas" / "quality-route.schema.json"
    if not route_schema.is_file():
        route_schema.parent.mkdir(parents=True, exist_ok=True)
        route_schema.write_text(ROUTE_SCHEMA + "\n", encoding="utf-8")
    plan_schema = project_root / ".agent" / "schemas" / "verification-plan.schema.json"
    if not plan_schema.is_file():
        plan_schema.parent.mkdir(parents=True, exist_ok=True)
        plan_schema.write_text(PLAN_SCHEMA + "\n", encoding="utf-8")
    return {
        "makefile": str(makefile),
        "skill": str(skill),
        "quality_route_schema": str(route_schema),
        "verification_plan_schema": str(plan_schema),
    }
