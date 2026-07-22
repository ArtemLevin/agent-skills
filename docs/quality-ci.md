# Quality CI and pull-request summary

AgentKit 0.9 generates a read-only GitHub Actions workflow that executes the same provider-neutral quality lifecycle used locally.

## Lifecycle

```text
full-history checkout
  -> configuration/provider validation
  -> merge-base resolution
  -> detached baseline worktree
  -> baseline quality analysis
  -> current quality analysis
  -> deterministic comparison
  -> configured quality gate
  -> bounded job summary
  -> artifact upload
  -> original gate exit code
```

The workflow calls `agentkit ci quality run-local`. It never invokes StrictaCode or another provider directly, so future providers can reuse the same CI contract.

## Install

```bash
agentkit ci quality install
```

The generated file is:

```text
.github/workflows/agentkit-quality.yml
```

AgentKit refuses to replace a differing workflow unless `--force` is supplied:

```bash
agentkit ci quality install --force
```

Preview without writing:

```bash
agentkit ci quality preview
```

## Local parity

```bash
agentkit ci quality run-local --base-ref main
agentkit ci quality summary --run-id latest
```

A clean checkout whose `HEAD` is also the resolved merge-base is rejected. Run from a feature branch, use a base ref behind `HEAD`, or make the intended worktree changes explicit.

## GitHub permissions

The generated workflow uses:

```yaml
permissions:
  contents: read
```

It writes the report through `$GITHUB_STEP_SUMMARY`; no pull-request write token is required. Optional workflow-command annotations are bounded and disabled by default.

## Configuration

```toml
[quality.ci]
enabled = true
workflow_path = ".github/workflows/agentkit-quality.yml"
python_version = "3.11"
base_branch = "main"
package_spec = "agent-skills-engineering-kit[quality]"
artifact_retention_days = 7
cache_enabled = true
annotations = false
```

`artifact_retention_days` must be between 1 and 90. The workflow always checks out with `fetch-depth: 0`.

## Artifacts

Native run artifacts remain under:

```text
.agent/state/runs/<run-id>/
```

The downloadable package is:

```text
.agent/state/runs/<run-id>/ci-artifacts/
├── quality-baseline.json
├── quality-current.json
├── quality-diff.json
├── quality-gate.json
├── quality-summary.md
└── ci-result.json
```

Provider status, bounded hotspots, and usage telemetry are included when available. Artifacts are uploaded even when the quality gate fails.

## Exit codes

```text
0  quality CI completed and the configured gate allowed completion
2  configuration, history, provider, or execution error
6  configured quality gate blocked completion
```

`report` and `warn` retain their existing non-blocking semantics. `enforce` returns exit code `6` for configured regressions.

## Make

```bash
make ai-quality-ci-install
make ai-quality-ci-preview
make ai-quality-ci-validate
make ai-quality-ci QUALITY_CI_BASE_REF=main
make ai-quality-ci-summary QUALITY_CI_SUMMARY_RUN_ID=latest
```
