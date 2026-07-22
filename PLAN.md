# AgentKit Development Plan

**Status:** Active roadmap  
**Last updated:** 2026-07-22  
**Current stable baseline:** AgentKit 0.11.0
**Target:** AgentKit 1.0 — measurable, quality-aware, provider-independent supervised autopilot for software engineering

---

## 1. Purpose

AgentKit combines engineering skills, Graphify repository context, controlled coding-agent execution, verification, adversarial review, token telemetry, phase-specific context compilation, and local caching.

The next development cycle must answer four questions that the current system cannot yet answer reliably:

1. Did the agent preserve or improve codebase health?
2. Which quality hotspots are relevant to the current task?
3. Which model and verification route is justified by the task risk?
4. Can these decisions be reproduced locally and in CI without loading unnecessary context?

The roadmap therefore evolves AgentKit through four successive capability layers:

```text
quality evidence
    -> quality regression control
    -> hotspot-aware context and routing
    -> CI, trends, evaluation, and model optimization
```

The objective is not maximum autonomy. The objective is a bounded engineering system that can work independently inside an explicitly configured safety corridor and produce evidence for every completion claim.

---

## 2. Current Baseline

The following foundation is already merged into `main`.

| Stage | Version | Capability | Status |
|---|---:|---|---|
| Foundation | 0.1 | Skills, policies, schemas, templates, validation | Complete |
| Graph-aware autopilot | 0.2 | Graphify integration, agent adapters, state machine, verification, review, completion gate | Complete |
| Telemetry and budgets | 0.3 | Usage ledger, token/call/time budgets, reports, budget gate | Complete |
| Context compiler and cache | 0.4 | Project profile, phase context, SQLite cache, fingerprint invalidation | Complete |
| Quality diagnostics | 0.5 | StrictaCode adapter, bounded snapshots, report-only evidence | Complete |
| Quality regression gate | 0.6 | Baseline/current comparison and configurable enforcement | Complete |
| Hotspot-aware context | 0.7 | Task-relevant quality context and cache invalidation | Complete |
| Quality-aware routing | 0.8 | Risk refinement and verification planning | Complete |
| Quality CI | 0.9 | Merge-base comparison and PR summaries | Complete |
| Trends and evaluation | 0.10 | Reproducible fixtures, outcome reports, and regressions | Complete |
| Model routing | 0.11 | Phase-aware OpenAI read-only planning/review and local mutation routing | Complete |

The current workflow is:

```text
user task
  -> Git preflight
  -> task triage
  -> Graphify context
  -> task packet
  -> quality-aware route and verification plan
  -> coding-agent implementation
  -> verification
  -> adversarial review
  -> bounded targeted fix
  -> functional, budget, scope, and quality gates
```

The current completion gate evaluates:

- verification results;
- adversarial review;
- changed-file scope;
- configured token/call/time budget;
- configured quality and maintainability regressions.

The remaining pre-1.0 work is contract freeze, migration safety, recovery, platform validation, and reproducible release engineering in PR 12.

---

## 3. Target Architecture

```text
                              User task
                                  |
                                  v
                    Project profile + task triage
                                  |
             +--------------------+--------------------+
             |                                         |
             v                                         v
      Quality provider                           Graphify provider
   health, hotspots, stats                 symbols, edges, paths, tests
             |                                         |
             +--------------------+--------------------+
                                  |
                                  v
                         Context compiler
             task + skills + graph + quality hotspots
                                  |
                                  v
                         Model/router adapter
                                  |
                                  v
                         Implementation phase
                                  |
                                  v
                 Verification + adversarial review
                                  |
                                  v
                    Post-change quality analysis
                                  |
                                  v
             Functional + budget + scope + quality gates
                                  |
                                  v
                      Human review / draft PR
```

### Component responsibilities

| Component | Responsibility | Must not become |
|---|---|---|
| Agent Skills | Engineering rules and phase contracts | Runtime orchestration engine |
| AgentKit runner | State transitions, gates, artifacts, safety | Source-code analyzer |
| Graphify | Repository relationship discovery | Proof of runtime behavior |
| StrictaCode adapter | Code-health metrics and hotspots | Automatic refactoring engine |
| Context compiler | Bounded task-specific context | Full repository dump |
| Quality gate | Detect configured regressions | Universal definition of correctness |
| Verification | Execute deterministic checks | Substitute for acceptance criteria |
| Model router | Select capable/cost-effective provider | Unbounded fallback loop |
| Human approval | Authorize risky or irreversible actions | Routine micromanagement |

---

## 4. Cross-Cutting Engineering Contracts

These rules apply to every planned pull request.

### 4.1 CLI and Make parity

Every user-facing capability must be available through both:

```text
agentkit <command>
make ai-<function>
```

A PR is incomplete when it exposes a Python API or CLI command without the matching Make target.

Make targets must:

- accept configuration through named Make variables;
- avoid shell-specific syntax where practical;
- work on Linux and Windows environments that provide GNU Make;
- print machine-readable JSON through the underlying CLI command;
- return the underlying AgentKit exit code.

### 4.2 Deterministic-first execution

Use deterministic code for:

- parsing JSON;
- hashing and invalidation;
- threshold evaluation;
- quality comparison;
- symbol and line-range resolution;
- tool-output compression;
- schema validation;
- report aggregation.

An LLM may interpret evidence, but it must not invent measurements that a local tool did not provide.

### 4.3 Report before enforcement

New signals are introduced in this order:

```text
report-only -> warning -> enforce
```

A new metric must not immediately block normal AgentKit runs. Enforcement requires:

- a stable schema;
- tests for false-positive boundaries;
- documented configuration;
- a clear unavailable-data policy;
- a migration path for existing projects.

### 4.4 Optional providers fail explicitly

Graphify, StrictaCode, external model APIs, and other providers are optional unless configured as required.

Provider states must distinguish:

```text
available
unavailable
unsupported
failed
partial
```

An unavailable optional provider creates a residual risk or warning. It must not be silently represented as a successful zero-valued result.

### 4.5 Bounded context

No integration may place its complete raw output into an agent prompt by default.

Every provider must expose:

- compact summary;
- bounded top-N evidence;
- artifact path for full details;
- explicit truncation flag;
- source fingerprint or revision.

### 4.6 Artifact and schema discipline

Every machine-readable artifact must contain:

- `version`;
- generation timestamp where relevant;
- provider/version metadata;
- source fingerprint or Git revision;
- explicit availability state;
- warnings and truncation state;
- stable JSON Schema.

Breaking artifact changes require a schema version increment and migration notes.

### 4.7 Local data and secrets

Derived repository data remains local by default under `.agent/` and is ignored by Git unless explicitly exported.

Never store in cache or run artifacts:

- API keys;
- access tokens;
- full environment dumps;
- credential files;
- raw secret values found in source or logs.

Provider secrets must be read from environment variables or platform credential stores.

### 4.8 Bounded retries and fallback

Every automatic loop must have a configured maximum:

- implementation calls;
- review calls;
- targeted-fix calls;
- provider fallback attempts;
- quality re-analysis calls.

A failed provider must not trigger an open-ended sequence of alternative model calls.

### 4.9 Backward-compatible configuration

New TOML sections must be optional and have safe defaults.

Until AgentKit 1.0:

- missing sections use defaults;
- unknown keys should produce a clear warning or validation error;
- `agentkit init` must not overwrite a customized configuration without explicit force;
- migration notes must accompany every version that adds configuration fields.

### 4.10 Evidence hierarchy

When signals conflict, use this order:

```text
source code and executed tests
  > reproducible tool output
  > static graph or metric inference
  > model interpretation
  > unsupported hypothesis
```

---

## 5. Roadmap Overview

| PR | Planned version | Theme | Primary outcome | Depends on |
|---|---:|---|---|---|
| PR 5 | 0.5.0 | Quality Diagnostics Provider | Structured StrictaCode evidence in report-only mode | 0.4 |
| PR 6 | 0.6.0 | Baseline and Quality Regression Gate | Before/after comparison and enforceable quality delta | PR 5 |
| PR 7 | 0.7.0 | Hotspot-Aware Context Compiler | Quality-ranked, line-aware minimal context | PR 5-6 |
| PR 8 | 0.8.0 | Quality-Aware Triage and Verification | Risk escalation and check selection from scoped evidence | PR 7 |
| PR 9 | 0.9.0 | Quality CI and PR Summary | Reproducible merge-base comparison in CI | PR 6-8 |
| PR 10 | 0.10.0 | Quality Trends and Evaluation Harness | Measure correctness, quality, tokens, and regressions over time | PR 9 |
| PR 11 | 0.11.0 | Model Router and Direct API Adapters | Capability-aware, measurable provider selection | PR 10 |
| PR 12 | 1.0.0 | Stabilization and Release | Schema freeze, migration safety, cross-platform release | PR 5-11 |

### Dependency graph

```text
PR 5 Quality Provider
  |
  v
PR 6 Baseline/Gate
  |
  +------------------+
  |                  |
  v                  v
PR 7 Context      PR 9 CI foundations
  |
  v
PR 8 Routing
  |
  +------------------+
                     v
                 PR 9 Quality CI
                     |
                     v
                 PR 10 Evals/Trends
                     |
                     v
                 PR 11 Model Router
                     |
                     v
                 PR 12 AgentKit 1.0
```

---

# PR 5 — Quality Diagnostics Provider

**Branch:** `agent/quality-diagnostics-provider`  
**Planned version:** `0.5.0`  
**Mode:** report-only

## Goal

Introduce a provider-neutral quality diagnostics interface and implement the first adapter for StrictaCode without changing the current completion decision.

The PR creates trustworthy, bounded, machine-readable quality evidence that later PRs can compare and enforce.

## Scope

### Required

- provider protocol and capability model;
- StrictaCode CLI adapter;
- structured `QualitySnapshot`;
- bounded project summary and hotspots;
- optional dependency group;
- SQLite snapshot caching;
- telemetry for quality tool calls;
- schemas, documentation, tests;
- CLI and Make commands.

### Non-goals

- no before/after gate;
- no completion blocking;
- no automatic refactoring;
- no copying StrictaCode metric formulas into AgentKit;
- no full StrictaCode JSON in an agent prompt;
- no Graphify/StrictaCode graph merge yet.

## Proposed package structure

```text
src/agentkit/quality/
├── __init__.py
├── base.py
├── models.py
├── strictacode.py
├── parser.py
├── cache.py
├── reporting.py
└── errors.py
```

## Provider contract

```python
class QualityProvider(Protocol):
    name: str

    def capabilities(self) -> QualityCapabilities: ...
    def doctor(self, project_root: Path) -> QualityProviderStatus: ...
    def analyze(
        self,
        project_root: Path,
        *,
        details: bool,
        include: list[str] | None,
        exclude: list[str] | None,
    ) -> QualitySnapshot: ...
```

`QualityCapabilities` must identify:

- supported languages;
- project/package/module/class/function detail support;
- line-number support;
- absolute-threshold support;
- comparison support;
- provider version.

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
max_packages = 5
max_modules = 5
max_classes = 10
max_methods = 15
max_functions = 15
include = []
exclude = ["vendor", "generated", ".venv", "node_modules"]
```

Allowed `details_policy` values:

```text
never
on_warning
always
```

Default behavior:

1. run short/project-level analysis;
2. if project status is elevated and policy is `on_warning`, run bounded details;
3. parse and persist compact evidence;
4. record full raw output only as a local artifact when diagnostic parsing fails.

## Artifacts

```text
.agent/state/runs/<run-id>/
├── quality-before.json
├── quality-hotspots.json
└── quality-provider.json
```

Initial `quality-before.json` structure:

```json
{
  "version": 1,
  "availability": "available",
  "provider": "strictacode",
  "provider_version": "...",
  "source_fingerprint": "...",
  "project": {
    "score": 34,
    "refactoring_pressure": 51,
    "overengineering_pressure": 19,
    "complexity_density": 14.2,
    "status": "normal"
  },
  "statistics": {
    "complexity": {"avg": 5, "max": 42, "p50": 3, "p90": 17},
    "refactoring_pressure": {"avg": 10, "max": 58, "p50": 8, "p90": 24},
    "overengineering_pressure": {"avg": 8, "max": 43, "p50": 5, "p90": 18}
  },
  "hotspots": [],
  "warnings": [],
  "truncated": false
}
```

## Cache identity

Use the existing SQLite cache with a separate namespace:

```text
namespace = quality_snapshot
```

Fingerprint input:

- provider name and version;
- StrictaCode configuration hash;
- source/control-file hashes;
- include/exclude patterns;
- details level;
- AgentKit quality parser version.

A cached snapshot is valid only when every fingerprint component and TTL matches.

## CLI

```bash
agentkit quality doctor
agentkit quality analyze
agentkit quality analyze --details
agentkit quality hotspots
agentkit quality show --run-id latest
```

## Make interface

```bash
make ai-quality-doctor
make ai-quality
make ai-quality-details
make ai-quality-hotspots
make ai-quality-show RUN_ID=<id>
```

## Runner integration

- quality analysis runs after triage and before context compilation;
- the tool call is recorded in `usage.json` as `kind=tool`, `phase=quality_before`;
- the compact snapshot path is added to the task packet;
- quality findings do not change run status in PR 5;
- unavailable optional quality data becomes a residual warning only.

## Tests

### Unit

- provider status parsing;
- supported/unsupported language distinction;
- StrictaCode JSON parsing;
- malformed and partial output;
- bounded top-N filtering;
- cache hit and invalidation;
- unavailable-provider handling;
- configuration validation.

### Contract

- fake provider implementing the protocol;
- fixture outputs for multiple StrictaCode versions;
- artifact schema validation;
- telemetry event creation.

### Integration

- temporary Python repository analyzed through a fake CLI executable;
- report-only AgentKit run remains ready when quality provider is optional and unavailable;
- required provider failure stops before implementation.

## Acceptance criteria

- normal AgentKit runs work without StrictaCode installed;
- quality extra can install StrictaCode explicitly;
- no metric is silently defaulted to zero;
- raw reports are not embedded into prompts;
- repeated unchanged analysis produces a cache hit;
- all quality commands have Make equivalents;
- quality artifacts validate against JSON Schema;
- completion semantics remain unchanged.

---

# PR 6 — Baseline and Quality Regression Gate

**Branch:** `agent/quality-regression-gate`  
**Planned version:** `0.6.0`

## Goal

Measure quality before and after an agent change, compare the snapshots, and optionally prevent a new maintainability regression.

## Scope

- baseline strategies;
- directional metric comparison;
- new/resolved/persisting hotspot comparison;
- absolute and delta thresholds;
- report/warn/enforce modes;
- quality completion gate;
- CLI and Make lifecycle commands;
- exit code and artifact contracts.

## Baseline strategies

```text
run_start   current working tree before implementation
merge_base  merge-base with configured base branch
file        explicit snapshot file
none        current-only absolute thresholds
```

Default local strategy:

```toml
baseline_strategy = "run_start"
```

Default CI strategy:

```toml
baseline_strategy = "merge_base"
base_branch = "main"
```

### Merge-base safety

AgentKit must never checkout the merge-base over the user's working tree.

Use one of:

- a detached temporary Git worktree under `.agent/worktrees/quality-baseline/`;
- provider analysis against an explicitly materialized temporary tree.

Temporary worktrees are removed on success and reported for manual cleanup after abnormal termination.

## Configuration

```toml
[quality]
mode = "report"
baseline_strategy = "run_start"
base_branch = "main"
unavailable_policy = "warn"

[quality.absolute]
score = 0
rp = 0
op = 0
density = 0.0

[quality.delta]
score = 5
rp = 5
op = 5
density = 3.0
new_critical_hotspots = 0
```

Values equal to zero disable the individual numeric threshold, except `new_critical_hotspots = 0`, which explicitly allows no new critical hotspot when the key is configured.

Allowed modes:

```text
report  store findings, never alter completion
warn    preserve completion but add residual risks
 enforce block ready_for_review on configured regression
```

Allowed unavailable policies:

```text
allow
warn
stop
```

## Artifacts

```text
.agent/state/runs/<run-id>/
├── quality-before.json
├── quality-after.json
├── quality-diff.json
└── quality-gate.json
```

`quality-diff.json` must include:

- baseline/current/delta for project metrics;
- new hotspots;
- resolved hotspots;
- persisting hotspots;
- changed hotspot severity;
- measurement comparability warnings.

A comparison is invalid when provider version, language, or incompatible configuration makes results non-comparable. Invalid comparison must be explicit and follow `unavailable_policy`.

## Execution order

```text
quality baseline
  -> implementation
  -> verification
  -> review
  -> targeted fix loop
  -> final verification
  -> final quality analysis
  -> quality comparison
  -> completion gate
```

Do not rerun full quality analysis after every small correction. Analyze after the final targeted-fix state unless a quality-specific fix is being validated explicitly.

## Completion integration

Add:

```json
{
  "quality_passed": true,
  "quality_available": true,
  "quality_regressions": []
}
```

Recommended exit-code reservation:

```text
0 success / ready
2 configuration or tool error
3 approval required
4 needs attention
5 budget exceeded
6 quality gate failed
```

## CLI

```bash
agentkit quality baseline
agentkit quality analyze --stage after
agentkit quality compare --run-id latest
agentkit quality gate --run-id latest
agentkit quality cycle
```

## Make interface

```bash
make ai-quality-baseline
make ai-quality-after
make ai-quality-compare RUN_ID=<id>
make ai-quality-gate RUN_ID=<id>
make ai-quality-cycle
```

## Tests

- positive/negative directional deltas;
- threshold boundary equality;
- multiple simultaneous violations;
- no configured threshold;
- unavailable/partial/non-comparable snapshots;
- new, resolved, and persisting hotspot identity;
- run-start baseline captured before agent mutation;
- temporary merge-base worktree cleanup;
- final quality run occurs after targeted fixes;
- completion and exit-code behavior in all modes.

## Acceptance criteria

- default mode is non-blocking;
- enforce mode blocks only configured regressions;
- legacy projects can use delta gates without passing absolute gates;
- baseline analysis cannot modify the user's worktree;
- comparison never treats missing data as improvement;
- every gate failure contains metric, baseline, current, delta, threshold, and scope;
- quality gate is represented in completion artifacts and final summary.

---

# PR 7 — Hotspot-Aware Context Compiler

**Branch:** `agent/hotspot-aware-context`  
**Planned version:** `0.7.0`

## Goal

Use quality hotspots as one bounded evidence source when selecting files and symbols for each agent phase.

The compiler must prioritize code that is both task-relevant and risky, not globally unhealthy but unrelated code.

## Scope

- quality-aware candidate ranking;
- line-aware hotspot enrichment;
- Graphify neighborhood fusion;
- hotspot context artifacts;
- configurable score components;
- token/character budgeting;
- explainable candidate selection.

## Candidate sources

```text
task keywords and paths
changed files
project profile roots
Graphify symbols/edges
StrictaCode hotspots
selected skill references
```

## Initial ranking model

The first deterministic implementation uses normalized components:

```text
0.45 task relevance
0.25 Graphify relationship proximity
0.20 quality hotspot severity
0.10 changed-file or explicit-path proximity
```

Rules:

- missing components are omitted and remaining weights are normalized;
- explicit user file/symbol references override ordinary ranking;
- global quality severity cannot select an unrelated file by itself;
- all component scores are persisted for explainability;
- weights are configuration, not permanent product truth.

## Configuration

```toml
[context.quality]
enabled = true
max_hotspots = 8
max_related_symbols = 12
include_project_summary = true
minimum_relevance = 0.15

[context.quality.weights]
task = 0.45
graph = 0.25
quality = 0.20
changed = 0.10
```

## Line-aware enrichment

For Python, resolve hotspot definitions with AST and add:

- file path;
- symbol kind and qualified name;
- start/end lines;
- signature;
- source hash.

For other languages:

- use provider line data when available;
- otherwise use Tree-sitter or Graphify location metadata where reliable;
- explicitly mark `location_status=unknown` instead of guessing.

## Context packet additions

```markdown
## Scoped quality evidence

- `src/service.py:281-332` — `process()`
  - complexity: 42
  - status: critical
  - relation to task: direct symbol match
  - Graphify: called by `ApiHandler.handle`
  - evidence status: extracted + provider metric
```

Full project metrics remain in artifacts, not in the phase prompt.

## Artifacts

```text
.agent/state/contexts/
├── <phase>-<key>.md
└── <phase>-<key>.json
```

JSON metadata adds:

- ranked candidates;
- component scores;
- quality hotspot IDs;
- line-resolution status;
- truncation decisions.

## CLI

```bash
agentkit context compile --quality --phase implementation --task "..."
agentkit context hotspots --task "..."
agentkit hotspot explain <file:symbol>
```

## Make interface

```bash
make ai-context-quality TASK="..." CONTEXT_PHASE=implementation
make ai-context-hotspots TASK="..."
make ai-hotspot-explain HOTSPOT="src/service.py:process"
```

## Tests

- quality-only candidate cannot override zero task relevance;
- explicit user path ranks first;
- Graphify relationship increases relevant candidate rank;
- no Graphify/quality provider fallback remains deterministic;
- Python line-range resolution;
- symbol rename invalidates cached context;
- score explanation is stable;
- output respects `max_context_chars` and top-N limits;
- review context receives diff-scoped quality evidence, not implementation noise.

## Acceptance criteria

- context remains bounded;
- every included hotspot has an explainable selection reason;
- unrelated global hotspots do not inflate the prompt;
- selected source changes invalidate the cache;
- quality evidence is separated from source-of-truth claims;
- Make and CLI produce equivalent artifacts.

---

# PR 8 — Quality-Aware Triage and Verification

**Branch:** `agent/quality-aware-routing`  
**Planned version:** `0.8.0`

## Goal

Use scoped quality evidence to choose the execution mode, selected skills, verification depth, and approval requirements.

## Scope

- quality-aware triage rules;
- verification-plan artifact;
- risk escalation matrix;
- characterization-test requirements;
- mode and approval escalation;
- quality-specific Make commands.

## Routing principles

- only evidence related to the task scope affects routing;
- project-wide poor health is context, not an automatic deep-mode trigger;
- risk escalation must be explainable;
- quality routing cannot weaken existing security, concurrency, migration, or public-API rules;
- deterministic rules run before model interpretation.

## Initial rule matrix

| Scoped evidence | Routing action |
|---|---|
| Target function complexity > 30 | Require targeted edge-case tests |
| Target function complexity > 40 | Require characterization test before structural rewrite |
| High RP in target module | Add `risk-based-testing` and regression-test requirement |
| High OP in target classes | Add `architecture-guard` and `engineering-balance` |
| High fan-in / centrality | Expand contract and component tests |
| High fan-out | Add integration checks for downstream dependencies |
| High RP and OP in target scope | Escalate to `deep` and require approval |
| Quality evidence unavailable | Preserve existing triage and add uncertainty warning |

## Verification plan

Create:

```text
.agent/state/runs/<run-id>/verification-plan.json
```

It records:

- selected commands;
- reason for each command;
- source evidence;
- targeted/full-suite escalation conditions;
- required characterization/regression tests;
- checks omitted because unavailable.

## Configuration

```toml
[quality.routing]
enabled = true
allow_mode_escalation = true
require_approval_on_crisis = true
characterization_complexity = 40
edge_case_complexity = 30
high_refactoring_pressure = 60
high_overengineering_pressure = 60
```

## CLI

```bash
agentkit quality triage --task "..."
agentkit quality plan-checks --task "..."
agentkit quality explain-route --run-id latest
```

## Make interface

```bash
make ai-quality-triage TASK="..."
make ai-quality-check TASK="..."
make ai-quality-plan TASK="..."
make ai-quality-route RUN_ID=<id>
```

## Tests

- local vs systemic evidence;
- related vs unrelated hotspot behavior;
- each routing rule boundary;
- no downgrade from deep to standard;
- approval required on scoped crisis state;
- unavailable provider fallback;
- verification-plan reason completeness;
- unchanged healthy task does not acquire unnecessary full-suite checks.

## Acceptance criteria

- routing decisions are deterministic and inspectable;
- quality evidence can escalate but not silently reduce risk;
- every selected check has a reason;
- characterization-test requirements are visible before implementation;
- normal low-risk tasks retain fast/standard efficiency;
- completion summary includes the applied quality route.

---

# PR 9 — Quality CI and PR Summary

**Branch:** `agent/quality-ci`  
**Planned version:** `0.9.0`

## Goal

Generate a reproducible GitHub Actions workflow that compares the pull-request branch with its merge-base, publishes structured artifacts, and enforces configured quality gates.

## Scope

- generated quality workflow;
- merge-base baseline analysis;
- current analysis and comparison;
- job summary;
- artifact upload;
- optional annotations;
- local CI preview;
- safe permissions and caching.

## Workflow design

```text
checkout fetch-depth: 0
  -> setup Python
  -> install AgentKit quality extra
  -> validate configuration
  -> resolve base and merge-base
  -> analyze baseline in temporary worktree
  -> analyze current tree
  -> compare and evaluate gate
  -> upload JSON artifacts
  -> publish GitHub job summary
  -> return quality exit code
```

AgentKit CI must call AgentKit's provider abstraction rather than hard-code StrictaCode commands into the generated workflow.

## Generated file

```text
.github/workflows/agentkit-quality.yml
```

Generation command must not overwrite a user-modified workflow without `--force`.

## Job permissions

Default:

```yaml
permissions:
  contents: read
```

Writing PR comments is optional and disabled by default. The first version uses `$GITHUB_STEP_SUMMARY`, which requires no pull-request write permission.

## Job summary

```markdown
## AgentKit Quality Report

| Metric | Baseline | Current | Delta | Threshold | Result |
|---|---:|---:|---:|---:|---|
| Project score | 34 | 35 | +1 | +5 | PASS |
| RP | 51 | 48 | -3 | +5 | PASS |
| OP | 19 | 22 | +3 | +5 | PASS |
| Density | 14.2 | 13.9 | -0.3 | +3.0 | PASS |

New critical hotspots: 0
Resolved hotspots: 1
Measurement warnings: none
```

## Artifacts

Upload:

```text
quality-baseline.json
quality-current.json
quality-diff.json
quality-gate.json
```

Retention is configurable and should default to a modest value.

## CLI

```bash
agentkit ci quality install
agentkit ci quality preview
agentkit ci quality run-local
agentkit ci quality summary --run-id latest
```

## Make interface

```bash
make ai-quality-ci-install
make ai-quality-ci-preview
make ai-quality-ci
make ai-quality-ci-summary RUN_ID=<id>
```

## Tests

- workflow golden file;
- no overwrite without force;
- base branch and merge-base resolution;
- shallow clone error message;
- temporary worktree cleanup;
- report-only and enforce behavior;
- artifact names and schema;
- job-summary rendering;
- paths containing spaces;
- Linux and Windows local preview where supported.

## Acceptance criteria

- CI and local comparison use the same Python gate implementation;
- baseline is never the current PR head;
- full Git history requirement is explicit;
- workflow runs read-only by default;
- quality artifacts are downloadable after failure;
- summary remains concise and bounded;
- CI can operate with a provider other than StrictaCode in the future.

---

# PR 10 — Quality Trends and Evaluation Harness

**Branch:** `agent/quality-trends-evals`  
**Planned version:** `0.10.0`

## Goal

Measure whether AgentKit changes improve accepted engineering outcomes, rather than merely reducing token counts or quality scores in isolation.

## Scope

- evaluation task format;
- repeatable fixture repositories;
- run/result collector;
- correctness, efficiency, and quality metrics;
- trend reports;
- baseline comparison between AgentKit versions/configurations;
- regression thresholds for the development of AgentKit itself.

## Evaluation task format

```yaml
id: python-local-bugfix-001
repository_fixture: fixtures/python_service
mode: standard
task: Fix duplicate retry scheduling
acceptance:
  commands:
    - [python, -m, pytest, tests/test_retry.py, -q]
  required_files:
    - tests/test_retry.py
  forbidden_files:
    - pyproject.toml
quality:
  allow_new_critical_hotspots: 0
budget:
  max_agent_calls: 4
```

Evaluation fixtures must be deterministic, versioned, and free of external service requirements unless explicitly marked as integration fixtures.

## Metrics

### Correctness

- acceptance checks passed;
- blocking review findings;
- scope violations;
- task ready-for-review rate;
- human acceptance where available.

### Efficiency

- agent calls;
- tool calls;
- input/output/cached/reasoning tokens when measured;
- duration;
- files and symbols included in context;
- context cache hit rate.

### Quality

- project metric delta;
- new/resolved hotspots;
- quality gate pass rate;
- hotspot recurrence;
- measurement availability.

### Composite reporting rule

Do not publish a single opaque universal score as the primary result.

Report dimensions separately and only use an aggregate for experiment ranking when its weights are explicit.

## Reports

```text
.agent/evals/<evaluation-id>/
├── manifest.json
├── runs/
├── summary.json
└── summary.md
```

## CLI

```bash
agentkit eval run evals/tasks/local-bugfix.yaml
agentkit eval suite evals/tasks
agentkit eval compare baseline.json current.json
agentkit quality trend --limit 50
agentkit quality regressions --limit 50
agentkit efficiency report --limit 50
```

## Make interface

```bash
make ai-eval EVAL_TASK=evals/tasks/local-bugfix.yaml
make ai-eval-suite EVAL_DIR=evals/tasks
make ai-eval-compare BASELINE=<file> CURRENT=<file>
make ai-quality-report REPORT_LIMIT=50
make ai-quality-trend REPORT_LIMIT=50
make ai-quality-regressions REPORT_LIMIT=50
make ai-quality-efficiency REPORT_LIMIT=50
```

## Experiment dimensions

The harness must support comparing:

```text
Graphify off/on
context cache off/on
quality context off/on
model A/model B
prompt compiler version
routing policy version
verification policy version
```

## Tests

- fixture isolation;
- deterministic manifest parsing;
- repeated-run aggregation;
- missing token usage;
- incomplete/failed runs;
- comparison schema compatibility;
- no secret leakage in reports;
- threshold boundary behavior;
- baseline preservation.

## Acceptance criteria

- an optimization cannot be declared successful solely because it uses fewer tokens;
- reports separate measured and unknown usage;
- correctness regressions are visible even when quality metrics improve;
- eval runs are reproducible from committed fixtures;
- AgentKit CI can run a small smoke suite;
- full suites remain opt-in due to provider cost.

---

# PR 11 — Model Router and Direct API Adapters

**Branch:** `agent/model-router-api-adapters`  
**Planned version:** `0.11.0`

**Implementation status:** complete on the PR branch; awaiting review and live opt-in provider evaluation.

## Goal

Add direct provider adapters and select models according to task risk, required capabilities, measured quality, and configured cost limits.

This PR is deliberately scheduled after the evaluation harness so routing decisions can be validated against engineering outcomes.

## Scope

- provider capability interface;
- OpenAI adapter;
- structured-output support;
- exact usage capture;
- prompt-cache metadata;
- deterministic phase routing policy;
- bounded fallback.

CLI adapters remain supported as fallback.

Anthropic, Ollama, and generic OpenAI-compatible adapters are deferred. PR 11 intentionally limits direct API support to OpenAI while retaining the local CLI as the only mutation-capable executor.

Implemented artifacts include phase-specific routing, the optional Responses API adapter, native review schemas, exact usage and cache metadata, bounded read-only retry/fallback, CLI diagnostics, Make targets, evaluation dimensions, installation resources, and mocked integration coverage. Live provider calls remain explicitly opt-in because they incur cost and require a user-supplied API key.

## Provider capabilities

```python
@dataclass(frozen=True)
class AgentCapabilities:
    structured_outputs: bool
    exact_usage: bool
    prompt_caching: bool
    session_resume: bool
    tool_calling: bool
    local_workspace_mutation: bool
    read_only_mode: bool
    reasoning_control: bool
    max_context_tokens: int | None
```

## Configuration

```toml
[models]
enabled = true
default_route = "standard"
max_retries = 1
max_fallbacks = 1

[models.targets.local]
provider = "cli"
platform = "codex"
command = ["codex", "exec", "{prompt}"]

[models.targets.openai-plan]
provider = "openai"
model = "configured-planning-model"
api_key_env = "OPENAI_API_KEY"
store = false

[models.targets.openai-review]
provider = "openai"
model = "configured-review-model"
api_key_env = "OPENAI_API_KEY"
store = false
structured_outputs = true

[models.routes.standard]
plan = "openai-plan"
implementation = "local"
review = "openai-review"
targeted_fix = "local"

[models.fallback]
plan = ["legacy-cli"]
review = ["legacy-cli"]
```

No API key is stored in TOML.

## Routing input

- task mode;
- scoped risk reasons;
- quality route;
- expected context size;
- required structured-output capability;
- provider availability;
- configured call/token/cost budget;
- evaluation evidence for the route.

Routing must not use live model marketing claims as evidence. Supported capabilities come from adapter contracts and configured policy.

## Structured outputs

Use provider-native schema-constrained output for:

- triage;
- review;
- quality interpretation when needed;
- completion summaries.

The deterministic parser remains as fallback, but invalid schema output counts as a failed call rather than being silently repaired by another unbounded model request.

## Prompt caching

Stable prompt components must be ordered before dynamic task data:

```text
system contract
skills and schema
project profile
phase contract
--- dynamic boundary ---
task
context evidence
current diff or failure
```

Cache identity includes versions/hashes of all stable components.

## CLI

```bash
agentkit models doctor
agentkit models list
agentkit models route --task "..."
agentkit providers test <provider>
agentkit run --route standard --task "..."
```

## Make interface

```bash
make ai-model-doctor
make ai-models
make ai-route TASK="..."
make ai-provider-test PROVIDER=openai
make ai TASK="..." MODEL_ROUTE=standard
```

## Tests

- provider capability negotiation;
- exact usage mapping;
- structured output success/failure;
- unavailable provider;
- single bounded fallback;
- no fallback after destructive/approval failure;
- route selection boundaries;
- secret redaction;
- prompt-prefix stability;
- mocked API integration.

## Acceptance criteria

- direct adapters expose usage without hidden estimation;
- routing decisions are persisted and explainable;
- fallback count is bounded;
- review remains an independent session/provider route;
- API keys never appear in artifacts or command output;
- CLI-only installation continues to work;
- eval results demonstrate that the default routes do not reduce acceptance quality.

---

# PR 12 — AgentKit 1.0 Stabilization and Release

**Branch:** `release/agentkit-1.0`  
**Planned version:** `1.0.0`

**Implementation status:** complete on the PR branch; awaiting cross-platform CI, review, and the manual opt-in OpenAI release evaluation.

## Goal

Freeze public contracts, harden installation and recovery, validate supported platforms, and publish a reproducible first stable release.

No major new feature enters this PR.

## Scope

### Public contract freeze

- CLI command names and exit codes;
- Make target names;
- configuration structure;
- artifact schemas;
- provider protocol;
- plugin/capability contract;
- state-directory layout.

### Installation and upgrade

- safe project update that merges generated changes instead of overwriting customization;
- configuration migration command;
- version compatibility check;
- rollback instructions;
- clear optional dependency groups;
- package metadata and release notes.

### Recovery

- incomplete run detection;
- temporary worktree cleanup;
- corrupted cache quarantine;
- resumable read-only/report phases where safe;
- explicit non-resumable mutation boundary;
- diagnostic bundle generation with secret redaction.

### Platform matrix

At minimum:

```text
Linux + Python 3.11-3.14
Windows + Python 3.11-3.14
Git repositories with paths containing spaces
projects with and without Make
projects with optional providers unavailable
```

### Documentation

- installation;
- upgrade;
- first run;
- configuration reference;
- CLI reference;
- Make reference;
- provider setup;
- quality gates;
- CI integration;
- troubleshooting;
- security model;
- architecture and extension guide.

## CLI

```bash
agentkit migrate check
agentkit migrate apply
agentkit self-test
agentkit diagnostics bundle
agentkit version --verbose
```

## Make interface

```bash
make ai-upgrade-check
make ai-migrate
make ai-self-test
make ai-diagnostics
make ai-release-check
```

## Release gates

- all unit, contract, integration, and golden tests pass;
- supported platform matrix passes;
- smoke eval suite has no correctness regression;
- artifact schemas are frozen and documented;
- no known P0/P1 findings;
- dependency and secret scans pass;
- install/upgrade/rollback are tested from 0.4 and later versions;
- release tag and package are reproducible from the commit.

## Acceptance criteria

- existing 0.x projects receive an actionable migration report;
- `agentkit init` no longer requires destructive force for ordinary upgrades;
- failure recovery does not hide partial code changes;
- stable commands and schemas are documented;
- one-command self-test verifies local readiness;
- the release remains supervised: no automatic merge, deployment, or irreversible operation is enabled by default.

---

## 6. Global Test Strategy

Each PR must add tests at the lowest reliable layer.

### Unit tests

- parsing;
- models;
- fingerprinting;
- threshold logic;
- ranking;
- routing;
- rendering.

### Contract tests

- provider protocols;
- artifact schemas;
- adapter output compatibility;
- CLI/Make parity;
- exit codes.

### Integration tests

- temporary Git repositories;
- fake external executables;
- Graphify/quality/context composition;
- runner state transitions;
- temporary worktrees;
- cache invalidation.

### Golden tests

- generated configuration;
- Makefile targets;
- GitHub workflow;
- compact context;
- job summary;
- migration output.

### End-to-end smoke tests

- report-only normal task;
- enforced quality regression;
- budget exceeded;
- deep approval required;
- provider unavailable;
- targeted fix followed by final gate;
- CI merge-base comparison.

### Failure injection

- malformed provider JSON;
- timeout;
- non-zero process exit;
- partial output;
- corrupted SQLite cache;
- stale fingerprint;
- missing Git history;
- worktree cleanup failure;
- invalid structured model output;
- unavailable fallback provider.

---

## 7. Observability and Success Metrics

AgentKit must optimize completed engineering outcomes, not isolated token counts.

### Primary outcome metrics

- ready-for-review rate;
- human acceptance rate where recorded;
- acceptance-test pass rate;
- blocking-review finding rate;
- quality-regression rate;
- unrelated-diff rate.

### Efficiency metrics

- input/output/cached tokens per accepted task;
- agent and tool calls per accepted task;
- context characters and files per phase;
- cache-hit rate;
- duration per accepted task;
- fraction of calls with measured usage.

### Quality metrics

- new critical hotspots per task;
- resolved hotspots;
- RP/OP/density delta;
- quality measurement availability;
- hotspot recurrence across recent runs.

### Initial operational goals

These are calibration goals, not permanent product promises:

- no correctness regression when enabling quality-aware context;
- no new critical hotspot in default enforce examples;
- every blocking gate has machine-readable evidence;
- every user-facing feature has CLI and Make parity;
- no hidden token or quality-value estimation;
- normal optional-provider failure remains recoverable;
- context and report outputs remain within configured bounds.

---

## 8. Security and Safety Model

### Command execution

- no shell interpolation for runner-owned commands;
- executable allowlist and denied patterns remain enforced;
- provider commands are represented as argv arrays;
- external tool paths are resolved explicitly;
- timeouts apply to every subprocess and API call.

### Repository protection

- preserve unrelated user changes;
- baseline analysis never checks out over the working tree;
- review remains read-only and diff-hash protected;
- destructive Git commands remain denied;
- commit, push, merge, and deployment remain explicit separate actions.

### Data handling

- redact secrets from stdout/stderr artifacts;
- never send complete repository data to a provider by default;
- record what context was sent to each model phase;
- allow local-only Ollama routes;
- document provider data boundaries.

### Approval gates

Human approval remains required for:

- deep mode when configured;
- database migrations;
- destructive operations;
- production deployment;
- breaking public API changes;
- authentication/authorization redesign;
- automatic PR publication when enabled in a future extension.

---

## 9. Configuration and Schema Migration Policy

### During 0.x

- additive configuration is preferred;
- defaults preserve previous behavior;
- schema version is explicit;
- breaking changes require migration code or clear one-release deprecation;
- deprecated keys produce warnings with replacement instructions.

### At 1.0

- stable CLI, Make, config, and artifact contracts are documented;
- schema migrations are supported through `agentkit migrate`;
- provider adapters declare compatibility ranges;
- unknown future artifact versions are rejected safely.

### Generated files

AgentKit must track generated-file metadata so upgrades can distinguish:

```text
unchanged generated file -> safe replacement
user-modified generated file -> merge or explicit conflict
missing file -> create
obsolete generated file -> report before removal
```

---

## 10. Risk Register

| Risk | Consequence | Mitigation |
|---|---|---|
| Quality metrics produce false confidence | Incorrect refactoring or gate | Treat metrics as evidence; require source/test validation |
| Legacy project fails absolute gates | Adoption blocked | Default to report and delta gates |
| Provider version changes JSON | Parsing failure | Version fixtures, capability/status detection, fail explicit |
| Quality output increases prompt size | Token regression | Bounded summaries, top-N, artifact references |
| Global hotspots distract task | Scope drift | Task relevance is mandatory ranking component |
| Merge-base analysis mutates worktree | User data loss | Temporary worktree only |
| Model router optimizes cost over quality | Lower acceptance rate | Build eval harness before routing |
| Multiple providers create configuration complexity | Operational errors | Capability interface, doctor command, safe defaults |
| Cache serves stale evidence | Wrong context/gate | Provider/config/source/version fingerprint and TTL |
| CI differs from local behavior | Unreproducible gate | Shared Python implementation and local preview |
| Trend reports encourage metric gaming | Cosmetic refactors | Keep correctness and acceptance as primary metrics |
| 0.x config upgrades overwrite customization | Lost settings | 1.0 migration/merge mechanism; no silent overwrite |

---

## 11. Definition of Ready for a Planned PR

A PR may enter implementation when:

- its dependency PRs are merged;
- scope and non-goals are explicit;
- artifact schemas are drafted;
- CLI and Make commands are named;
- failure/unavailable behavior is defined;
- migration impact is known;
- acceptance criteria are testable;
- external provider versions are not hard-coded without a compatibility policy.

---

## 12. Definition of Done for Every PR

A roadmap PR is complete only when:

- implementation matches declared scope;
- new commands have Make equivalents;
- configuration defaults preserve old behavior;
- artifacts have schemas and versions;
- unit and integration tests cover success and failure;
- documentation includes examples and limitations;
- CI passes skill validation, tests, compile checks, and CLI smoke checks;
- no unrelated diff remains;
- residual risks are documented;
- draft PR contains an operator-focused verification section.

---

## 13. Deferred Backlog

The following ideas are intentionally deferred until the quality and evaluation layers provide evidence that they are necessary.

### Test-impact learning

Map changed symbols to historically failing tests and select targeted checks before full-suite escalation.

### Validated project memory

Persist only merged architectural decisions, confirmed invariants, and reproduced regressions. Do not store raw conversations or unverified hypotheses.

### Graphiti temporal memory

Consider only when cross-run temporal facts cannot be represented adequately through validated local artifacts.

### LangGraph orchestration

Consider when the plain Python state machine requires durable distributed checkpoints, parallel agents, or long-lived human-in-the-loop workflows.

### Parallel implementation agents

Defer until evals demonstrate that parallelism improves accepted outcomes enough to justify extra cost and merge complexity.

### Web dashboard

Defer until CLI/JSON reports and GitHub summaries are stable. The CLI remains the source of truth.

### Automatic commit, push, and draft PR

May be added as an explicitly enabled delivery plugin. Automatic merge and production deployment remain outside the default safety model.

---

## 14. Immediate Next Action

Review and merge **PR 11 — Model Router and Direct API Adapters**.

Before merge:

1. review the local-mutation boundary and secret-handling paths;
2. confirm the mocked OpenAI adapter, retry, fallback, schema, and packaging tests;
3. run an explicitly authorized live provider smoke test with a user-supplied API key;
4. run at least one opt-in evaluation comparing the configured route with the CLI baseline;
5. record any quality or acceptance regression before changing route defaults.

After PR 11, begin **PR 12 — AgentKit 1.0 Stabilization and Release**. No additional direct provider adapter is required for 1.0; Anthropic, Ollama, and generic compatible endpoints remain deferred until evaluation evidence justifies them.
