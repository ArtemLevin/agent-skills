# Make reference

GNU Make is optional. `.agent/Makefile.agent` exposes the same operations as the CLI and is included through a bounded managed block in the project Makefile.

Graphify bootstrap and update targets:

```bash
make ai-graph-install GRAPHIFY_PLATFORM=agents
make ai-graph
```

`ai-graph-install` is idempotent and delegates to `agentkit graph install --platform ...`. AgentKit resolves the dependency executable from `PATH` or its own tool environment.

Release targets:

```bash
make ai-upgrade-check
make ai-migrate
make ai-self-test
make ai-diagnostics
make ai-release-check
```

`ai-release-check` combines the read-only migration check and self-test. It does not build, publish, merge, deploy, or call a paid provider. Projects without Make use the equivalent CLI commands directly.
