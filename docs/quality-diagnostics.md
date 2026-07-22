# Quality diagnostics provider

AgentKit 0.5 adds report-only code-health evidence through an optional provider adapter. The first provider is StrictaCode.

## Install

The default AgentKit installation remains lightweight and does not require StrictaCode.

```bash
uv tool install "agent-skills-engineering-kit[quality]"
```

When AgentKit is installed from Git:

```bash
uv tool install "git+https://github.com/ArtemLevin/agent-skills.git@agent/quality-diagnostics-provider#egg=agent-skills-engineering-kit[quality]"
```

## Configuration

```toml
[quality]
enabled = true
provider = "strictacode"
required = false
mode = "report"
details_policy = "on_warning"
cache_enabled = true
cache_ttl_seconds = 86400
timeout_seconds = 900
command = ["strictacode"]
max_packages = 5
max_modules = 5
max_classes = 10
max_methods = 15
max_functions = 15
include = []
exclude = ["vendor", "generated", ".venv", "node_modules"]
```

`details_policy` supports:

- `never` — project summary only;
- `on_warning` — summary first, then bounded details when project status is `warning`, `critical`, or `emergency`;
- `always` — bounded detailed analysis immediately.

AgentKit 0.5 supports only `mode = "report"`. Quality evidence does not block completion. Enforcement is reserved for the baseline and regression-gate stage.

## CLI and Make

```bash
agentkit quality doctor
agentkit quality analyze
agentkit quality analyze --details
agentkit quality hotspots --run-id latest
agentkit quality show --run-id latest
```

Equivalent project commands:

```bash
make ai-quality-doctor
make ai-quality
make ai-quality-details
make ai-quality-hotspots
make ai-quality-show
```

## Artifacts

```text
.agent/state/runs/<run-id>/
├── quality-before.json
├── quality-hotspots.json
├── quality-provider.json
└── usage.json
```

Raw provider output is written only when the provider command fails or JSON parsing fails:

```text
quality-raw.stdout.txt
quality-raw.stderr.txt
```

## Cache

Snapshots use the existing SQLite database with namespace `quality_snapshot`. Cache identity includes:

- provider and provider version;
- details level;
- parser version;
- top-N limits;
- include/exclude settings;
- content hashes of supported source and control files.

A truncated source fingerprint disables cache reuse. Missing provider metrics are preserved as `null`; AgentKit never converts missing values to zero.

## Runner integration

During a normal `agentkit run`, quality analysis is performed before the coding-agent call. The compact task-packet entry contains only:

- availability;
- provider metadata;
- project-level metrics;
- hotspot count;
- bounded warnings;
- artifact paths.

The complete StrictaCode report is never embedded into the prompt. An unavailable optional provider becomes a residual warning while preserving existing completion semantics. When `required = true`, unavailable, unsupported, or failed quality evidence stops the run before implementation.

## Evidence limits

StrictaCode metrics are maintainability signals. They do not prove a behavioral defect. Recommendations must be confirmed against source code and executed tests.

AgentKit configuration `include` and `exclude` participates in source fingerprinting. StrictaCode itself reads `.strictacode.yml`, `.strictacode.yaml`, or `.strictacode.json` from the project root; mirror provider-specific loader scope there when exact analysis scoping is required.
