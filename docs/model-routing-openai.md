# OpenAI model routing

AgentKit 0.11 adds an optional direct OpenAI Responses API adapter for read-only workflow phases. The coding-agent CLI remains the executor for phases that can edit the repository.

## Safety boundary

| Phase | Direct OpenAI allowed | Local CLI required |
|---|---:|---:|
| `plan` | yes | no |
| `implementation` | no | yes |
| `review` | yes | no |
| `targeted_fix` | no | yes |

The direct adapter receives no local tools. Configuration loading rejects a route that assigns a non-mutating OpenAI target to `implementation` or `targeted_fix`. AgentKit also avoids provider fallback after a mutating phase fails, because the workspace may contain a partial change.

## Install

The default installation remains CLI-only. Install the optional SDK when OpenAI routes are enabled:

```bash
python -m pip install -e '.[openai]'
```

Set the key in the environment, not in TOML:

```bash
export OPENAI_API_KEY='...'
```

## Configuration

```toml
[models]
enabled = true
default_route = "standard"
max_retries = 1
max_fallbacks = 1

[models.targets.local]
provider = "cli"
platform = "codex"
command = ["codex", "exec", "{prompt}"]
timeout_seconds = 1800

[models.targets.openai-plan]
provider = "openai"
model = "your-configured-openai-model"
api_key_env = "OPENAI_API_KEY"
store = false
prompt_caching = true

[models.targets.openai-review]
provider = "openai"
model = "your-configured-openai-model"
api_key_env = "OPENAI_API_KEY"
store = false
structured_outputs = true

[models.routes.standard]
plan = "openai-plan"
implementation = "local"
review = "openai-review"
targeted_fix = "local"

[models.fallback]
plan = ["legacy-cli"]
review = ["legacy-cli"]
```

Model names are deliberately configuration values. AgentKit does not embed a changing provider default in the runtime.

## Inspect before running

```bash
agentkit models doctor
agentkit models list
agentkit models route --task "Fix duplicate writes" --explain
agentkit providers test openai --target openai-plan
```

These commands do not make a paid API request. Add `--live` to `providers test` only when an actual request is intended.

Select a configured route for a run:

```bash
agentkit run --route standard --task "Fix duplicate writes"
```

`--agent` and `--route` are mutually exclusive: the former is an explicit one-command override, while the latter selects a phase route.

## Provider behavior

- Uses the Responses API with `store = false` unless explicitly enabled.
- Uses native JSON Schema structured output for review.
- Sends a deterministic prompt cache key derived from the stable prompt prefix.
- Captures input, output, cached-input, reasoning, and total tokens from provider metadata.
- Redacts bearer tokens and API-key-like values from provider errors.
- Retries transient connection, timeout, rate-limit, and server errors within `max_retries`.

AgentKit persists routing evidence in each run directory:

- `model-route.json` — chosen target and rationale per phase;
- `model-attempts.json` — primary, retry, and fallback attempts with usage;
- `prompt-prefix-<phase>.json` — stable-prefix hash and character counts;
- `usage.json` — totals by phase and provider.

## Operational notes

Prompt caching is opportunistic; a cache key does not guarantee a cache hit. Use `cached_input_tokens` in usage metadata as the measured signal. Review output that violates the schema is treated as a failed call and can use the configured read-only fallback.

Provider data retention and abuse-monitoring behavior are controlled by the OpenAI account and endpoint settings. Keep `store = false` unless stored Responses are intentionally required, and review the current OpenAI data controls before sending sensitive repository context.

## OpenAI references

- [Responses API migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Data controls](https://developers.openai.com/api/docs/guides/your-data)
