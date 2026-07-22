from __future__ import annotations

# Fallback resources used only when AgentKit cannot find the full source kit.
BUILTIN_AGENT_MD = """# Engineering Agent Contract

Deliver the smallest evidence-backed change that fully satisfies the task.

1. Run task triage before substantial repository work.
2. Query Graphify first when a graph exists and the task spans code relationships.
3. Compile phase-specific context and read only selected skills and minimal source context.
4. Establish verifiable acceptance criteria.
5. Keep the diff focused and preserve unrelated changes.
6. Select tests by regression risk, not coverage percentage.
7. Perform adversarial review and fix only blocking findings.
8. Stop when required checks pass and no P0/P1 finding remains.

Never claim an unexecuted check passed. Never commit, push, deploy, or perform irreversible operations unless the user explicitly authorizes that action.
"""

_CORE_SKILL_TEMPLATE = """---
name: {name}
description: >
  {description}
---

# Purpose

{purpose}

# Inputs

- user task
- current task packet
- relevant project evidence

# Workflow

1. Read the task packet.
2. Gather only evidence required for this responsibility.
3. Return a compact structured result.
4. Escalate uncertainty instead of guessing.

# Decision rules

- Stay within the assigned responsibility.
- Prefer measured evidence over assumptions.
- Do not broaden the diff or context without a reason.

# Output

Return decisions, evidence, unresolved risks, and the smallest next action.

# Stop conditions

Stop when the responsibility is satisfied or further work requires new evidence.
"""

CORE_SKILLS = {
    "task-triage": (
        "Use before substantial repository work to classify task risk, choose fast, standard, or deep mode, and activate only necessary skills.",
        "Route the task to the smallest safe engineering workflow.",
    ),
    "repository-context": (
        "Use to obtain minimal repository context, preferring scoped Graphify queries before broad file reads when a graph is available.",
        "Find relevant symbols, dependencies, tests, and unknowns without reading the whole repository.",
    ),
    "context-compiler": (
        "Use to compile phase-specific minimal context, build or inspect the project profile, and reuse valid cached context without rereading unchanged files.",
        "Produce a bounded context packet for plan, implementation, review, or targeted-fix phases.",
    ),
    "requirements-contract": (
        "Use when code behavior changes to turn the request into verifiable acceptance criteria, non-goals, and compatibility constraints.",
        "Create a precise contract that prevents scope drift.",
    ),
    "change-planner": (
        "Use for standard or deep tasks to map each intended change to files, symbols, reasons, verification, and rollback concerns.",
        "Produce an actionable plan rather than restating the request.",
    ),
    "implementation": (
        "Use after context and contract are established to apply the smallest complete and reviewable code change.",
        "Implement the approved behavioral delta while preserving project conventions.",
    ),
    "verification-router": (
        "Use after implementation to select the narrowest commands that can prove changed behavior and relevant contracts.",
        "Choose evidence-producing checks without defaulting to an expensive full suite.",
    ),
    "adversarial-review": (
        "Use after checks to try to disprove correctness and report only evidenced P0 through P3 findings.",
        "Find real defects rather than praise or stylistic preferences.",
    ),
    "token-telemetry": (
        "Use to inspect measured token, call, and duration usage, enforce budgets, and identify expensive workflow phases without inventing missing metrics.",
        "Measure efficiency while preserving correctness and required verification.",
    ),
    "delivery-summary": (
        "Use at the end of a task to report actual changes, commands executed, results, and residual risks without a verbose diary.",
        "Provide a factual handoff that distinguishes proof from assumption.",
    ),
}


def render_core_skill(name: str) -> str:
    description, purpose = CORE_SKILLS[name]
    return _CORE_SKILL_TEMPLATE.format(
        name=name,
        description=description,
        purpose=purpose,
    )
