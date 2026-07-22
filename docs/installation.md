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
agentkit --project-root /path/to/project init --skip-graphify-install
agentkit --project-root /path/to/project self-test
```

Initialization installs `.agent/`, a managed Make include, and Git ignore blocks. It records `.agent/installation.json`; commit that manifest with the other AgentKit project files. AgentKit never stores API-key values in project configuration.

Use `agentkit version --verbose` to inspect package, Python, platform, optional dependency, and contract versions.
