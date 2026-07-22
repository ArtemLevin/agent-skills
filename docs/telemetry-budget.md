# Telemetry and budget controller

AgentKit 0.3 records every runner-owned command in `.agent/state/runs/<run-id>/usage.json`.

## What is measured

- agent calls by phase: `plan`, `implementation`, `review`, `targeted_fix`;
- local tool calls: Graphify update/query and verification commands;
- wall-clock duration;
- input, output, cached-input, reasoning, and total tokens when the CLI exposes them;
- calls whose token usage is unavailable.

AgentKit parses common JSON and text usage formats. Missing token metadata remains explicitly unknown; it is never estimated silently.

## Budget configuration

```toml
[budget]
enabled = true
soft_input_tokens = 30000
hard_input_tokens = 60000
soft_output_tokens = 8000
hard_output_tokens = 16000
soft_agent_calls = 4
hard_agent_calls = 7
soft_duration_seconds = 1800
hard_duration_seconds = 3600
unknown_usage_policy = "warn"

[budget.phase_agent_call_limits]
plan = 1
implementation = 1
review = 2
targeted_fix = 1
```

Zero disables an individual numeric limit. `unknown_usage_policy` supports:

- `allow` — keep partial totals without a warning;
- `warn` — keep partial totals and surface the caveat;
- `stop` — prevent another model call after an unmeasured call.

A soft limit is informational. A hard token/duration overrun changes the run status to `budget_exceeded`; a reached hard call/phase limit prevents the next model call.

## CLI and Make interface

```bash
agentkit usage
agentkit usage --run-id <id>
agentkit budget
agentkit budget --run-id <id>
agentkit report --limit 20
```

Equivalent project commands:

```bash
make ai-usage
make ai-budget
make ai-report REPORT_LIMIT=20
make ai-telemetry
make ai-usage RUN_ID=<id>
```

`agentkit init --force` refreshes an existing project's generated `.agent/Makefile.agent` and default configuration. Review local configuration changes before using `--force`.

## Artifacts

```text
.agent/state/runs/<run-id>/
├── usage.json
├── budget.json
└── completion.json
```

The aggregate report includes readiness rate, totals, averages per run, and per-phase usage. Optimize against accepted tasks, not isolated token counts.
