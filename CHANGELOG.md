# Changelog

All notable AgentKit changes are documented here. The project follows semantic versioning from 1.0 onward.

## 1.0.2 — 2026-07-22

- Run AgentKit-managed Graphify updates in deterministic local `--code-only` mode so projects containing documentation do not require an LLM API key or trigger provider usage.
- Preserve incremental `--update`, directed graphs, and local graph queries over the resulting `graph.json`.
- Decode Graphify subprocess output explicitly as UTF-8 and set Python UTF-8 environment flags to preserve Cyrillic Windows paths.
- Add regression coverage for keyless code-only graph creation, incremental updates, absolute executables, and UTF-8 subprocess settings.

## 1.0.1 — 2026-07-22

- Resolve Graphify from AgentKit's own Python or `uv tool` environment when the dependency executable is not exported to the user `PATH`.
- Automatically run the project-scoped Graphify skill installer during `agentkit init` using the resolved absolute executable.
- Add the idempotent repair command `agentkit graph install --platform <platform>` and `make ai-graph-install`.
- Extend `agentkit doctor` with package, executable-source, project-skill, and repair diagnostics while preserving the existing `installed` and `version` fields.
- Add Windows/Linux regression coverage for hidden dependency executables, paths with spaces and Cyrillic characters, and absolute-command execution.

## 1.0.0 — 2026-07-22

- Freeze CLI commands, exit codes, Make targets, configuration version, provider phases, artifact schemas, and state layout.
- Add safe project migrations, installation manifests, backups, update candidates, and compatibility checks from AgentKit 0.4 onward.
- Preserve customized project resources during ordinary `init` and migration operations.
- Add atomic run lifecycle state, incomplete-run detection, mutation boundaries, safe read-only resume, and non-destructive worktree handling.
- Quarantine corrupted SQLite caches and recreate an empty cache without deleting evidence.
- Add one-command self-test, verbose version diagnostics, and bounded redacted diagnostic bundles.
- Validate Linux and Windows on Python 3.11–3.14 and add reproducible wheel/sdist release gates.
- Keep direct API execution limited to read-only OpenAI planning and review; local CLI execution remains the only mutation path.
