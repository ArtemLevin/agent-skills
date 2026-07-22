# Quality baseline and regression gate

AgentKit 0.6 adds deterministic before/after comparison and an optional
quality regression gate on top of the report-only provider introduced in 0.5.

## Lifecycle

```text
quality baseline
  -> implementation
  -> verification
  -> adversarial review
  -> targeted fixes
  -> final quality analysis
  -> comparison
  -> quality gate
  -> completion
```

The final analysis runs once after the last targeted-fix state. Missing metrics
are never converted to zero or interpreted as improvement.

## Baseline strategies

- `run_start`: analyze the current worktree before the first model call.
- `merge_base`: analyze a detached temporary worktree at the merge-base with
  `quality.base_branch`; the user's worktree is never checked out or replaced.
- `file`: load `quality.baseline_file`.
- `none`: disable delta checks and evaluate only configured absolute thresholds.

## Modes

- `report`: persist violations without affecting completion.
- `warn`: preserve completion and add violations to residual risks.
- `enforce`: block `ready_for_review` and return exit code `6`.

`quality.unavailable_policy` is independent:

- `allow`: continue with explicit missing evidence.
- `warn`: continue and add residual risks.
- `stop`: block when current evidence or required comparison is unavailable.

## Commands

```bash
agentkit quality baseline
agentkit quality analyze --stage after
agentkit quality compare --run-id latest
agentkit quality gate --run-id latest
agentkit quality cycle
```

Make equivalents:

```bash
make ai-quality-baseline
make ai-quality-after
make ai-quality-compare QUALITY_RUN_ID=latest
make ai-quality-gate QUALITY_RUN_ID=latest
make ai-quality-cycle
```

## Artifacts

```text
.agent/state/runs/<run-id>/
├── quality-baseline.json
├── quality-before.json
├── quality-after.json
├── quality-diff.json
├── quality-gate.json
└── completion.json
```

`quality-diff.json` includes baseline/current/delta values, comparability
warnings, and new/resolved/persisting/changed hotspots. `quality-gate.json`
contains every violation rather than stopping after the first one.

## Threshold semantics

Current AgentKit treats higher project score, refactoring pressure,
overengineering pressure, and complexity density as worse.

A threshold is violated only when the value is strictly greater than the
configured limit. Equality passes.

Numeric zero disables an absolute or metric-delta threshold. The explicitly
configured `new_critical_hotspots = 0` means that no new critical hotspot is
allowed when delta comparison is active.

## Migration

Running `agentkit init` adds missing baseline keys, threshold tables, Make
targets, schemas, and the `quality-regression-gate` skill without overwriting
existing values. Existing projects remain in non-blocking `mode = "report"`
until the user explicitly changes the mode.
