# AgentKit 1.0 public contracts

AgentKit 1.x treats CLI command names, exit codes, Make targets, configuration version 1, model phase names, provider capability fields, artifact schemas, and `.agent/state` layout as compatibility surfaces.

Additive optional fields and commands may appear in minor releases. Removing or renaming a stable field, changing its type or meaning, making an optional dependency mandatory, or changing a stable exit code requires a major release.

All machine-readable schemas are version 1. Payloads that historically lacked a `version` property identify the schema version through `x-agentkit-schema-version`. New AgentKit-owned lifecycle, migration, installation, self-test, and diagnostic payloads contain `version: 1` directly.

The stable phase vocabulary is `plan`, `implementation`, `review`, and `targeted_fix`. Direct OpenAI execution is read-only. Implementation and targeted fix require `local_workspace_mutation=true` and therefore use the configured local CLI.

The state layout keeps `.agent/state/latest` and `.agent/state/runs/<run-id>/`. `run.json` records status, phase, mutation boundary, timestamps, worktrees, and recovery guidance. Additional artifacts may be added without changing existing meanings.
