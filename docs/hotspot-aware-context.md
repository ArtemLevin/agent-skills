# Hotspot-aware context compiler

AgentKit 0.7 ranks bounded quality hotspots against the current task and available Graphify evidence before opening implementation context.

## Ranking model

Each candidate receives explainable component scores:

- `task_score` — lexical relevance to the requested change;
- `graph_score` — whether the file or symbol appears in available Graphify evidence;
- `quality_score` — bounded severity derived from status, complexity, RP, OP, or provider rank.

The default weighted score is:

```text
total = 0.60 × task relevance
      + 0.25 × graph evidence
      + 0.15 × quality severity
```

Task relevance is intentionally dominant. A globally severe but unrelated hotspot must not expand the task context by itself.

## CLI

```bash
agentkit hotspot-context compile --task "Fix session persistence"
agentkit hotspot-context compile --task-file task.md --run-id latest --limit 8
agentkit hotspot-context explain --task "Fix session persistence" --file src/recorder.py --symbol _write_session
```

## Make

```bash
make ai-context-hotspots TASK="Fix session persistence"
make ai-context-quality TASK="Fix session persistence"
make ai-hotspot-explain TASK="Fix session persistence" HOTSPOT_FILE=src/recorder.py HOTSPOT_SYMBOL=_write_session
```

## Inputs and output

The compiler prefers `quality-after.json`, then falls back to `quality-before.json`. It reads only bounded hotspot records and at most 100 KB of Graphify evidence. Python line ranges are resolved with `ast`; unsupported languages keep explicit `null` ranges.

Output is written under `.agent/state/contexts/` and cached in the existing SQLite database under namespace `hotspot_context`. Cache identity includes task, source snapshot, graph evidence, selected limits, and content hashes of candidate files.

Quality metrics remain navigation evidence. The generated context does not prove a defect, runtime relationship, or required refactoring.
