# Troubleshooting

## Graphify package exists but command is unavailable

AgentKit 1.0.1+ resolves Graphify from both the user `PATH` and AgentKit's own Python or `uv tool` environment. Run:

```bash
agentkit doctor
agentkit graph install --platform agents
```

The `graphify` section reports `package_installed`, `executable_found`, `executable_source`, `project_skill_installed`, and an actionable repair command. A normal `uv tool install "git+https://github.com/ArtemLevin/agent-skills.git"` no longer requires `--with-executables-from graphifyy` for AgentKit's internal operations.

If explicit repair still reports that the executable cannot be resolved, reinstall AgentKit and inspect `agentkit version --verbose`. `agentkit init --skip-graphify-install` remains available for intentionally minimal or diagnostic installations.

## Graphify asks for an LLM API key

AgentKit 1.0.2+ invokes Graphify with `--code-only` for managed graph updates. This builds the code graph locally through deterministic extraction, skips documentation/media semantic extraction, and does not require an LLM API key.

After upgrading, run:

```bash
agentkit graph update
agentkit graph query "Where is lesson persistence implemented?"
```

For a one-off semantic graph that includes documentation, invoke Graphify directly and explicitly choose its backend or provide the backend's credentials. This is outside the default AgentKit workflow so an ordinary graph refresh cannot silently trigger paid provider usage.

On Windows, AgentKit requests UTF-8 subprocess output and sets `PYTHONUTF8=1` plus `PYTHONIOENCODING=utf-8`; paths containing Cyrillic characters should therefore remain readable in JSON output.

## Graphify query starts from AgentKit schemas or unrelated nodes

AgentKit 1.0.3+ passes the original task text directly to `graphify query`. It no longer prepends generic words such as `task`, `return`, or `smallest`, which could become stronger lexical seeds than the user's identifiers.

The first managed graph refresh also creates or updates a bounded block in `.graphifyignore`:

```gitignore
# BEGIN AGENTKIT
.agent/
.agents/
graphify-out/
# END AGENTKIT
```

User-authored ignore rules outside that block are preserved. When the block is first installed or changed, AgentKit performs one full local rebuild instead of an incremental update so stale `.agent` schema and skill nodes do not survive in `graph.json`. Later refreshes return to `--update`.

For an existing noisy graph, upgrade AgentKit and run:

```bash
agentkit graph update
agentkit graph query "Where is lesson.json written atomically?"
```

For manual investigation, use exact identifiers when known:

```bash
graphify explain "_synchronize_lesson_files"
graphify path "_synchronize_lesson_files" "atomic_write_text"
graphify query "lesson.json _synchronize_lesson_files atomic_write_text" --context call
```

Increasing the token budget does not improve wrong seed selection; narrow the query or inspect an exact node instead.

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
