# Agent Skills Engineering Kit

Graph-aware **supervised autopilot** for AI-assisted software development, with optional phase-aware OpenAI routing.

The repository combines two layers:

```text
Agent Skills  -> engineering discipline, risk routing, tests, review, stop rules
Graphify      -> local code graph and scoped repository context
AgentKit CLI  -> executable workflow that connects them to a coding-agent CLI
```

The default workflow does not commit, push, merge, deploy, or perform destructive migrations. It prepares a verified change for human review. Direct OpenAI API execution is restricted to read-only planning and review; repository edits continue through the configured local coding-agent CLI.

## What is included

- `AGENT.md` — global engineering contract;
- `skills/` — focused planning, implementation, testing, review, and Graphify skills;
- `policies/` — quality gates, severity model, token budget, and tool permissions;
- `src/agentkit/` — executable Python orchestrator;
- `schemas/` — machine-readable task, plan, review, and completion contracts;
- `templates/` — ADR, plan, review, and delivery templates;
- `scripts/` — skill validation and compact repository mapping;
- `tests/` and GitHub Actions — automated validation.

## Workflow

```text
request
  -> Git preflight
  -> task triage
  -> Graphify update and scoped query
  -> task packet
  -> coding-agent implementation
  -> configured or discovered checks
  -> adversarial review
  -> at most N targeted fix iterations
  -> completion gate
  -> human review
```

### Execution modes

| Mode | Intended use | Behavior |
|---|---|---|
| `fast` | text, docs, trivial local edits | minimal context and checks |
| `standard` | ordinary bug fixes and small features | plan, implementation, targeted checks, review |
| `deep` | auth, migrations, data, concurrency, production | explicit approval plus specialist skills |

Deep mode stops before implementation unless `--approve-deep` is supplied.

## Installation

Requirements:

- Python 3.11+;
- Git;
- one supported coding-agent CLI, such as Codex;
- GNU Make is optional but convenient.

Install directly from GitHub:

```bash
uv tool install "git+https://github.com/ArtemLevin/agent-skills.git"
```

The distribution depends on the official `graphifyy` package, so the `graphify` CLI is installed with AgentKit.

For local development:

```bash
git clone https://github.com/ArtemLevin/agent-skills.git
cd agent-skills
python -m pip install -e .
```

Install the optional OpenAI adapter with:

```bash
python -m pip install -e '.[openai]'
```

## Initialize a target project

```bash
cd /path/to/your-project
agentkit init --platform agents
```

This command:

1. creates `.agent/` with the contract, skills, policies, schemas, and templates;
2. writes `.agent/agentkit.toml`;
3. registers Graphify as a project-scoped Agent Skill;
4. creates `.agent/Makefile.agent` and includes it from the project `Makefile`;
5. adds `graphify-out/` and `.agent/state/` to `.gitignore`.

Commit the installation before running autopilot:

```bash
git add .agent .agents Makefile .gitignore
git commit -m "chore: install AgentKit"
```

A clean tree is required by default so the runner can attribute changes to one task.

## First checks

```bash
agentkit doctor
agentkit self-test
agentkit graph update
```

`doctor` reports whether Git, the configuration, Graphify, and the configured agent executable are available.

## Daily use

### Full supervised autopilot

```bash
make ai TASK="Fix duplicate material generation for one lesson"
```

Equivalent direct command:

```bash
agentkit run --task "Fix duplicate material generation for one lesson"
```

### Task from a file

```bash
make ai TASK_FILE=tasks/fix-writer-thread.md
```

### Plan without editing

```bash
make ai-plan TASK="Add PostgreSQL retention policy"
```

### Explicit deep-mode approval

```bash
agentkit run \
  --mode deep \
  --approve-deep \
  --task-file tasks/database-migration.md
```

### Dry run

```bash
agentkit run --dry-run --task "Explain how recording reaches transcription"
```

A dry run creates triage, Graphify context, task packet, and implementation prompt but does not invoke the coding agent.

## Main commands

```text
agentkit init
agentkit run
agentkit plan
agentkit graph update
agentkit graph query "question"
agentkit check
agentkit doctor
agentkit status
agentkit models doctor
agentkit models list
agentkit models route --task "question"
agentkit providers test openai
agentkit migrate check
agentkit self-test
agentkit diagnostics bundle
agentkit version --verbose
```

Make aliases:

```text
make ai
make ai-plan
make ai-graph
make ai-check
make ai-doctor
make ai-status
make ai-upgrade-check
make ai-self-test
make ai-diagnostics
```

## Configuration

Project configuration lives at `.agent/agentkit.toml`.

```toml
[agent]
platform = "codex"
command = ["codex", "exec", "{prompt}"]
timeout_seconds = 1800

[graphify]
enabled = true
required = false
directed = true
query_budget = 1200

[workflow]
default_mode = "auto"
require_clean_tree = true
require_review = true
deep_requires_approval = true
max_fix_iterations = 1

[verification]
commands = [
  ["python", "-m", "pytest", "-q"],
  ["ruff", "check", "."]
]

[scope]
max_changed_files = 20

[models]
enabled = false
default_route = "standard"
max_retries = 1
max_fallbacks = 1
```

Every command is stored as an argv array. AgentKit does not evaluate configured commands through a shell.

See [OpenAI model routing](docs/model-routing-openai.md) for phase targets, environment-key configuration, structured review output, bounded fallback, and run artifacts. Provider tests are diagnostic-only unless `--live` is supplied.

## Coding-agent adapters

The default Codex adapter invokes:

```text
codex exec <generated prompt>
```

The command is configurable and supports two placeholders:

- `{prompt}` — generated task packet and instructions;
- `{phase}` — `implementation`, `review`, or `targeted-fix`.

Examples:

```toml
[agent]
platform = "aider"
command = ["aider", "--message", "{prompt}"]
```

```toml
[agent]
platform = "custom"
command = ["my-agent", "run", "--phase", "{phase}", "--prompt", "{prompt}"]
```

## Graphify integration

AgentKit uses Graphify as a **query-first navigation index**:

1. update or build `graphify-out/graph.json`;
2. request one task-scoped subgraph;
3. pass only that result to the agent;
4. require critical relationships to be confirmed in source code and tests.

Graphify output is never treated as proof of runtime correctness. Dynamic imports, dependency injection, Qt signals, callbacks, ORM behavior, concurrency, and configuration-dependent behavior still require source and test evidence.

## Run artifacts

Each run creates:

```text
.agent/state/runs/<run-id>/
├── triage.json
├── graph.json
├── task-packet.json
├── implementation-prompt.md
├── implementation-command.json
├── model-route.json
├── model-attempts.json
├── prompt-prefix-<phase>.json
├── verification.json
├── review.json
└── completion.json
```

`.agent/state/` is ignored by Git.

## Safety model

AgentKit uses several independent controls:

- clean Git tree by default;
- executable allowlist and denied command fragments;
- no shell interpolation for runner-owned commands;
- explicit approval for deep mode;
- limited fix iterations;
- review phase must not mutate the diff;
- maximum changed-file count;
- no automatic commit, push, merge, or deployment;
- fail-closed behavior when review output is not valid structured JSON.

The coding agent still has its own sandbox and approval policy. AgentKit complements that sandbox; it does not replace it.

## Development

```bash
python scripts/validate_skills.py
python -m unittest discover -s tests -v
python -m compileall -q src scripts tests
```

Or:

```bash
make validate
```

## Status

AgentKit 1.0 is a stable supervised-autopilot release: autonomous context gathering, implementation, checking, and review, followed by a human decision. OpenAI model routing is opt-in and the CLI-only path remains the default. Autonomous commits, merges, and deployments remain outside the runtime contract.

## Documentation

- [Beginner guide](docs/agentkit-guide.md)
- [Installation](docs/installation.md)
- [Upgrade and rollback](docs/upgrade-guide.md)
- [CLI reference](docs/cli-reference.md)
- [Configuration reference](docs/config-reference.md)
- [Troubleshooting](docs/troubleshooting.md)
- [AgentKit 1.0 contracts](docs/public-contracts-1.0.md)
- [Architecture](docs/architecture.md)
- [Security model](docs/agentkit-security.md)
- [OpenAI model routing](docs/model-routing-openai.md)
- [Skill activation matrix](docs/activation-matrix.md)
- [Adoption guide](docs/adoption-guide.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT. Graphify is also distributed under the MIT license.
