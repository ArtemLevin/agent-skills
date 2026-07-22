# Quality trends and evaluation harness

AgentKit 0.10 evaluates engineering outcomes on deterministic fixture repositories. Reports keep correctness, efficiency, and quality separate; reduced token usage cannot compensate for failed acceptance checks or a lower ready-for-review rate.

## Evaluation task

```yaml
version: 1
id: python-local-bugfix-001
repository_fixture: evals/fixtures/python_service
mode: standard
task: Fix duplicate retry scheduling and add a regression test.
repetitions: 2
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
```

YAML parsing uses PyYAML when installed and a deterministic built-in subset parser otherwise. JSON manifests are also accepted. Secret-like experiment keys are rejected.

## Isolation

Each run is executed in:

```text
.agent/evals/<evaluation-id>/runs/run-001/workspace/
```

The source fixture is hashed before and after execution. AgentKit initializes and commits a deterministic Git baseline only inside the copied workspace. Selected AgentKit artifacts are copied into `agent-run/` before the disposable workspace is removed.

## Metrics

### Correctness

- acceptance command pass rate;
- required and forbidden file constraints;
- ready-for-review rate;
- blocking findings;
- scope violations;
- optional human acceptance.

### Efficiency

- agent and tool calls;
- duration;
- measured token fields;
- unknown agent calls reported separately;
- context file/symbol counts where available;
- context cache hit rate where available.

### Quality

- measurement availability;
- quality gate pass rate;
- project metric deltas;
- new and resolved hotspots;
- new critical hotspots;
- hotspot recurrence.

No opaque universal score is emitted.

## CLI

```bash
agentkit eval run evals/tasks/python-local-bugfix.yaml
agentkit eval run evals/tasks/python-local-bugfix.yaml --runs 3
agentkit eval suite evals/tasks --smoke
agentkit eval suite evals/tasks
agentkit eval compare baseline-summary.json current-summary.json
agentkit quality report --limit 50
agentkit quality trend --limit 50
agentkit quality regressions --limit 50
agentkit efficiency report --limit 50
```

A comparison returns `regression` when any configured regression threshold is strictly exceeded. Equality passes. Correctness regressions dominate efficiency improvements.

## Make

```bash
make ai-eval EVAL_TASK=evals/tasks/python-local-bugfix.yaml
make ai-eval-suite EVAL_DIR=evals/tasks EVAL_SMOKE=1
make ai-eval-compare EVAL_BASELINE=baseline.json EVAL_CURRENT=current.json
make ai-quality-report REPORT_LIMIT=50
make ai-quality-trend REPORT_LIMIT=50
make ai-quality-regressions REPORT_LIMIT=50
make ai-quality-efficiency REPORT_LIMIT=50
```

## Reports

```text
.agent/evals/<evaluation-id>/
├── manifest.json
├── runs/
│   └── run-001/
│       ├── agent-run/
│       └── result.json
├── summary.json
└── summary.md
```

Reports redact common credential formats, secret-like keys, and bound command output tails. Missing token usage remains unknown rather than becoming zero.

## Opt-in CI smoke suite

The generated quality workflow can run only manifests marked `smoke: true` after the merge-base quality cycle:

```toml
[quality.ci]
eval_smoke_enabled = true
eval_manifest_directory = "evals/tasks"
eval_repetitions = 1
```

The default remains `false` because agent/provider calls can have material cost. Smoke results are appended to the GitHub Job Summary and uploaded with the quality artifacts.
