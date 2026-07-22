# Troubleshooting

## Graphify package exists but command is unavailable

AgentKit 1.0.1 resolves Graphify from both the user `PATH` and AgentKit's own Python or `uv tool` environment. Run:

```bash
agentkit doctor
agentkit graph install --platform agents
```

The `graphify` section reports `package_installed`, `executable_found`, `executable_source`, `project_skill_installed`, and an actionable repair command. A normal `uv tool install "git+https://github.com/ArtemLevin/agent-skills.git"` no longer requires `--with-executables-from graphifyy` for AgentKit's internal operations.

If explicit repair still reports that the executable cannot be resolved, reinstall AgentKit and inspect `agentkit version --verbose`. `agentkit init --skip-graphify-install` remains available for intentionally minimal or diagnostic installations.

## Incomplete run

Run `agentkit status`. If `mutation_started` is true and `mutation_completed` is false, inspect the working tree manually. Do not repeat the mutating command until the partial diff is understood. Diagnostic collection never resets or hides that diff.

## Migration preserves a file

Compare the current file with `.agent/update-candidates/<path>`. Merge the desired changes manually, then update or recreate the installation manifest by completing a reviewed migration. Backups are under `.agent/backups/`.

## Corrupted context cache

AgentKit runs SQLite `PRAGMA quick_check`. A corrupt database and its WAL sidecars are moved under `.agent/cache/quarantine/<timestamp>/`; an empty cache is created. Quarantined evidence is not deleted automatically.

## Temporary quality worktree remains

Inspect `.agent/worktrees/` and `git worktree list`. AgentKit refuses to force-remove a dirty worktree. Preserve or commit useful changes, then remove it explicitly with Git.

## OpenAI unavailable

This is a warning while model routing is disabled. If an active route requires OpenAI, install the `openai` extra and supply the configured environment variable. `providers test openai` is offline unless `--live` is explicitly passed.

## Support bundle

Run `agentkit diagnostics bundle`. The ZIP contains version, self-test, migration, installation, dependency-executable, and lifecycle metadata. It excludes source, diffs, prompts, and raw provider output, and redacts credential-shaped values.
