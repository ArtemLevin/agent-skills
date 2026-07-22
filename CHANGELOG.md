# Changelog

All notable AgentKit changes are documented here. The project follows semantic versioning from 1.0 onward.

## 1.0.0 — 2026-07-22

- Freeze CLI commands, exit codes, Make targets, configuration version, provider phases, artifact schemas, and state layout.
- Add safe project migrations, installation manifests, backups, update candidates, and compatibility checks from AgentKit 0.4 onward.
- Preserve customized project resources during ordinary `init` and migration operations.
- Add atomic run lifecycle state, incomplete-run detection, mutation boundaries, safe read-only resume, and non-destructive worktree handling.
- Quarantine corrupted SQLite caches and recreate an empty cache without deleting evidence.
- Add one-command self-test, verbose version diagnostics, and bounded redacted diagnostic bundles.
- Validate Linux and Windows on Python 3.11–3.14 and add reproducible wheel/sdist release gates.
- Keep direct API execution limited to read-only OpenAI planning and review; local CLI execution remains the only mutation path.
