from __future__ import annotations

from pathlib import Path

MAKEFILE_HOTSPOT = r'''

# BEGIN AGENTKIT HOTSPOT CONTEXT
HOTSPOT_RUN_ID ?= latest
HOTSPOT_LIMIT ?= 12
HOTSPOT_OUTPUT ?=
HOTSPOT_FILE ?=
HOTSPOT_SYMBOL ?=

.PHONY: ai-context-hotspots ai-context-quality ai-hotspot-explain

ai-context-hotspots:
	$(AGENTKIT) hotspot-context compile $(if $(TASK),--task "$(TASK)",) $(if $(TASK_FILE),--task-file "$(TASK_FILE)",) --run-id "$(HOTSPOT_RUN_ID)" --limit "$(HOTSPOT_LIMIT)" $(if $(HOTSPOT_OUTPUT),--output "$(HOTSPOT_OUTPUT)",)

ai-context-quality: ai-context-hotspots

ai-hotspot-explain:
	$(AGENTKIT) hotspot-context explain --task "$(TASK)" --file "$(HOTSPOT_FILE)" $(if $(HOTSPOT_SYMBOL),--symbol "$(HOTSPOT_SYMBOL)",) --run-id "$(HOTSPOT_RUN_ID)"
# END AGENTKIT HOTSPOT CONTEXT
'''

SKILL = '''---
name: hotspot-aware-context
description: >
  Use before implementation context is opened to rank bounded quality hotspots against task relevance and available Graphify evidence.
---

# Purpose

Select the smallest explainable set of quality-relevant files and symbols without allowing global code-health scores to broaden task scope.

# Inputs

- current engineering task;
- latest bounded quality snapshot;
- available Graphify evidence;
- context size and candidate-count limits;
- source files required for deterministic line resolution.

# Workflow

1. Load the latest bounded quality snapshot.
2. Score task relevance before quality severity.
3. Use Graphify evidence as structural support, not runtime proof.
4. Resolve Python symbol line ranges deterministically.
5. Emit bounded candidates, component scores, reasons, warnings, and artifact paths.

# Decision rules

- Task relevance is the dominant ranking factor.
- An unrelated severe hotspot must not enter context only because it has a high quality score.
- Missing Graphify evidence is explicit and produces a zero graph component.
- Read source and tests before treating a hotspot as a concrete defect.
- Keep candidate count and content size bounded by context configuration.

# Output

Return a ranked candidate list with task, graph, quality and total scores, exact line ranges when available, compact reasons, warnings and the generated context artifact path.

# Stop conditions

Stop when the bounded ranked context is generated, every missing input is explicit, and no additional repository content is required merely to improve a global quality score.
'''

SCHEMA = '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/hotspot-context.schema.json",
  "title": "AgentKit hotspot-aware context",
  "type": "object",
  "required": ["version", "task", "source_snapshot", "source_fingerprint", "graph_available", "cache_key", "fingerprint", "cache_hit", "candidates", "warnings", "content_chars"],
  "properties": {
    "version": {"const": 1},
    "task": {"type": "string"},
    "source_snapshot": {"type": "string"},
    "source_fingerprint": {"type": "string"},
    "graph_available": {"type": "boolean"},
    "cache_key": {"type": "string"},
    "fingerprint": {"type": "string"},
    "cache_hit": {"type": "boolean"},
    "candidates": {"type": "array", "items": {"type": "object"}},
    "warnings": {"type": "array", "items": {"type": "string"}},
    "content_chars": {"type": "integer"}
  }
}'''


def _append_once(path: Path, content: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker not in text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + content, encoding="utf-8")


def ensure_hotspot_context_files(project_root: Path) -> dict[str, str]:
    makefile = project_root / ".agent" / "Makefile.agent"
    _append_once(makefile, MAKEFILE_HOTSPOT, "# BEGIN AGENTKIT HOTSPOT CONTEXT")
    skill = project_root / ".agent" / "skills" / "hotspot-aware-context" / "SKILL.md"
    if not skill.is_file():
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(SKILL, encoding="utf-8")
    schema = project_root / ".agent" / "schemas" / "hotspot-context.schema.json"
    if not schema.is_file():
        schema.parent.mkdir(parents=True, exist_ok=True)
        schema.write_text(SCHEMA + "\n", encoding="utf-8")
    return {"makefile": str(makefile), "skill": str(skill), "schema": str(schema)}
