# CLI reference

AgentKit 1.0 freezes the following top-level commands: `init`, `run`, `plan`, `graph`, `profile`, `context`, `cache`, `check`, `doctor`, `status`, `usage`, `budget`, `report`, `models`, `providers`, `quality`, `ci`, `eval`, `efficiency`, `hotspot-context`, `migrate`, `self-test`, `diagnostics`, and `version`.

Release and recovery commands:

```bash
agentkit migrate check
agentkit migrate apply
agentkit self-test
agentkit diagnostics bundle
agentkit version --verbose
agentkit run --resume <run-id> --task "..."
agentkit plan --resume <run-id> --task "..."
```

Resume is permitted only before the mutation boundary. A run interrupted during implementation or targeted fix is never replayed automatically.

## Stable exit codes

| Code | Meaning |
|---:|---|
| 0 | Success |
| 1 | Valid empty result |
| 2 | Invocation, configuration, dependency, provider, or execution error |
| 3 | Explicit human approval required |
| 4 | Task, verification, evaluation, self-test, or migration readiness failed |
| 5 | Hard budget exceeded |
| 6 | Quality gate rejected the change |

An external program's return code is evidence inside JSON output; it is not a stable AgentKit process code.
