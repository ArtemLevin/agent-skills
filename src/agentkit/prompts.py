from __future__ import annotations

import json
from pathlib import Path

from .graphify import GraphContext
from .models import ReviewReport, TriageResult


def implementation_prompt(
    *,
    project_root: Path,
    task: str,
    triage: TriageResult,
    graph: GraphContext,
    plan_only: bool,
) -> str:
    skill_lines = "\n".join(f"- .agent/skills/{name}/SKILL.md" for name in triage.selected_skills)
    action = (
        "Produce a concrete implementation plan only. Do not edit files or run mutating commands."
        if plan_only
        else "Complete the task end-to-end. Do not stop after planning. Edit the code and run targeted checks."
    )
    graph_text = graph.output or f"Unavailable: {graph.warning or 'no graph context'}"
    return f"""You are running under AgentKit supervised autopilot.

Read and obey `.agent/AGENT.md`. Use progressive disclosure: read only these selected skills unless evidence requires another one:
{skill_lines}

Execution mode: {triage.mode.value}
Risk reasons: {json.dumps(triage.risk_reasons, ensure_ascii=False)}
Project root: {project_root}

USER TASK
{task}

GRAPHIFY SCOPED CONTEXT
{graph_text}

OPERATING REQUIREMENTS
- {action}
- Treat Graphify as a navigation index, not as proof of runtime correctness.
- Confirm critical relationships in source code and tests.
- Keep the diff minimal and preserve unrelated user changes.
- Comments explain rationale, invariants, constraints, or contracts, never obvious syntax.
- Do not claim a check passed unless it was actually executed successfully.
- Do not create commits, push branches, merge PRs, deploy, or perform destructive migrations.
- Finish with a compact factual summary of changed files, checks actually run, and residual risks.
"""


def review_prompt(*, task: str, diff: str, triage: TriageResult) -> str:
    return f"""Perform an adversarial code review. Do not edit any files.

Original task:
{task}

Execution mode: {triage.mode.value}

Current diff:
{diff or '[no textual diff available]'}

Try to disprove correctness against the user task. Check acceptance behavior, regressions, error handling, data safety, concurrency, security, public contracts, and test adequacy. Report only evidenced findings. P0/P1 are blocking; P2/P3 are non-blocking.

Your final output MUST contain one JSON object and no prose after it:
{{
  "verdict": "approved" or "changes_required",
  "findings": [
    {{
      "severity": "P0|P1|P2|P3",
      "file": "path or empty",
      "issue": "precise problem",
      "evidence": "why it is real",
      "smallest_fix": "minimal correction"
    }}
  ]
}}
"""


def fix_prompt(*, task: str, review: ReviewReport) -> str:
    payload = json.dumps(review.to_dict(), ensure_ascii=False, indent=2)
    return f"""Apply a targeted correction for the blocking review findings below.

Original task:
{task}

Review report:
{payload}

Rules:
- Fix only P0/P1 findings.
- Do not broaden scope or perform unrelated refactoring.
- Re-run the narrowest checks relevant to the correction.
- Do not create commits, push, deploy, or perform irreversible operations.
"""
