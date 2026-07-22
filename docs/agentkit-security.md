# AgentKit security model

AgentKit provides orchestration-level guardrails around a coding-agent CLI. It does not replace the agent's native sandbox.

## Trust boundaries

1. **User task** — untrusted instructions that may be ambiguous or destructive.
2. **Graphify output** — trusted for navigation only, not runtime correctness.
3. **Coding agent** — capable of changing files and invoking commands inside its own sandbox.
4. **Runner-owned commands** — verification and Graphify commands executed directly by AgentKit.
5. **Git repository** — source of change attribution and final human review.

## Controls

### Clean tree

The default configuration refuses to run implementation when Git already contains changes. This avoids confusing user work with agent work.

### No shell evaluation

Configured runner commands are argv arrays and are passed directly to `subprocess.run`. Shell operators, command substitution, and pipelines are not interpreted.

### Command policy

Runner-owned commands are checked against:

- an executable allowlist;
- denied command fragments;
- an execution timeout.

This policy does not inspect every command executed internally by a third-party coding agent. Use the agent's sandbox and approval settings as the primary command boundary.

### Deep-mode approval

Tasks related to authentication, data migrations, concurrency, secrets, production, destructive data changes, and public contracts are routed to deep mode. The runner creates context and stops before implementation unless `--approve-deep` is supplied.

### Read-only review invariant

AgentKit hashes the Git diff before and after the review phase. Any mutation during review is converted into a blocking P1 finding.

### Bounded loops

The runner performs at most the configured number of targeted fix iterations. It never enters an open-ended implementation/review loop.

### Fail closed

If review output cannot be parsed as the required JSON contract, AgentKit creates a blocking P1 finding rather than assuming approval.

## Actions deliberately excluded from MVP

- automatic commit;
- automatic push;
- force push;
- merge;
- production deployment;
- destructive migrations;
- secret rotation;
- permanent data deletion.

These may later be added as separately authorized plugins with explicit approval gates and auditable policies.
