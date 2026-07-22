# Configuration reference

Project configuration is `.agent/agentkit.toml`. The stable 1.0 configuration schema version is `1`. Unknown sections are retained by migrations.

| Section | Purpose |
|---|---|
| `agent` | Local mutation-capable CLI command and timeout |
| `models` | Opt-in phase routing, bounded retry, and fallback |
| `graphify` | Repository graph availability and query budget |
| `workflow` | Mode, clean-tree, review, approval, and fix limits |
| `budget` | Token, call, duration, and unknown-usage policy |
| `context` | Project profile, SQLite cache, bounds, and TTL |
| `verification` | Explicit argv checks and timeout |
| `scope` | Maximum changed-file count |
| `security` | Executable allowlist and denied command fragments |
| `quality` | Provider, cache, details, and regression thresholds |
| `evaluation` | Fixture isolation, repetitions, and report limits |

Commands are argv arrays and are never evaluated through a shell. OpenAI targets reference an environment-variable name such as `OPENAI_API_KEY`; they never contain its value. Mutation phases must resolve to a local CLI target.

Run `agentkit migrate check` after upgrading the package and `agentkit self-test` after changing configuration.
