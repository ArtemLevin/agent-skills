# Context compiler and cache

AgentKit 0.4 adds a deterministic context layer that can be called independently from Make before any agent phase.

## Project profile

```bash
agentkit profile show
agentkit profile refresh
make ai-profile
make ai-profile-refresh
```

The profile records detected languages, package managers, source/test roots, frameworks, verification commands, control files, and a fingerprint. It is written to `.agent/project-profile.json` and is regenerated only when its fingerprint changes or refresh is requested.

## Compile context

```bash
agentkit context compile \
  --phase implementation \
  --task "Fix duplicate material generation"
```

Make equivalent:

```bash
make ai-context \
  CONTEXT_PHASE=implementation \
  TASK="Fix duplicate material generation"
```

Supported phases are `plan`, `implementation`, `review`, and `targeted_fix`. The compiler includes:

- compact project profile;
- phase contract;
- only selected skill summaries;
- bounded candidate file paths;
- top-level Python class/function signatures;
- explicit context-boundary warnings.

It does not embed full source files or the complete repository graph.

Compiled Markdown is written under `.agent/state/contexts/` unless `--output` or `CONTEXT_OUTPUT` is supplied.

## SQLite cache

The local cache lives at `.agent/cache/context.db` by default. Cache identity includes the normalized task, phase, mode, compiler version, profile fingerprint, selected candidate contents, and selected skill contents.

```bash
agentkit cache stats
agentkit cache list --limit 20
agentkit cache prune --max-age-days 30
agentkit cache clear --yes
```

Make equivalents:

```bash
make ai-cache-stats
make ai-cache-list CACHE_LIMIT=20
make ai-cache-prune CACHE_MAX_AGE_DAYS=30
make ai-cache-clear
make ai-context-maintain
```

`ai-context-maintain` refreshes the profile, prunes stale entries, and prints cache statistics.

A cache entry is never returned when its fingerprint differs or its TTL expired. Cache misses are safe and only cause deterministic recompilation.

## Configuration

```toml
[context]
enabled = true
cache_enabled = true
cache_path = ".agent/cache/context.db"
profile_path = ".agent/project-profile.json"
max_profile_files = 5000
max_candidate_files = 12
max_symbols_per_file = 20
max_context_chars = 16000
cache_ttl_seconds = 604800
stale_after_days = 30
```

The profile and cache are derived local artifacts and are added to `.gitignore` by `agentkit init`.
