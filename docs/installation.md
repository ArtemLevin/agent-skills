# Installation

AgentKit 1.0 supports Linux and Windows with Python 3.11–3.14. Git is required; GNU Make is optional.

```bash
python -m pip install agent-skills-engineering-kit
```

For read-only OpenAI planning and review:

```bash
python -m pip install 'agent-skills-engineering-kit[openai]'
```

Initialize a Git project:

```bash
agentkit --project-root /path/to/project init --platform agents
agentkit --project-root /path/to/project self-test
```

Initialization installs `.agent/`, a managed Make include, and Git ignore blocks. It records `.agent/installation.json`; commit that manifest with the other AgentKit project files. AgentKit never stores API-key values in project configuration.

## Automatic Graphify bootstrap

`graphifyy` is a required AgentKit dependency. Since AgentKit 1.0.1, `agentkit init` resolves the `graphify` executable from either the user `PATH` or AgentKit's own Python/`uv tool` environment, then automatically runs:

```bash
graphify install --project --platform agents
```

This means the ordinary installation is sufficient:

```bash
uv tool install "git+https://github.com/ArtemLevin/agent-skills.git"
agentkit init --platform agents
```

The dependency executable does not need to be exported separately with `uv tool install --with-executables-from graphifyy` for AgentKit's internal Graphify operations.

To repair or change the project-scoped platform registration explicitly:

```bash
agentkit graph install --platform agents
```

Equivalent Make command:

```bash
make ai-graph-install GRAPHIFY_PLATFORM=agents
```

Use `--skip-graphify-install` only for intentionally minimal installations, package diagnostics, or environments where Graphify project resources must not be written.

Use `agentkit version --verbose` to inspect package, Python, platform, optional dependency, executable-resolution, and contract versions. `agentkit doctor` reports whether Graphify came from `PATH` or the AgentKit tool environment and whether the project skill is installed.
