# Quality-aware triage and verification

AgentKit 0.8 refines deterministic task triage with bounded, task-scoped quality evidence. The route can add skills, test requirements, deep-mode escalation, and approval requirements, but it cannot reduce an existing risk classification.

## Routing order

```text
base task triage
  -> Graphify task context
  -> quality baseline
  -> hotspot-aware context
  -> quality route
  -> verification plan
  -> implementation
```

Project-wide poor health is not sufficient to escalate a task. Only candidates selected by the hotspot-aware context compiler participate in routing.

## Default thresholds

```toml
[quality.routing]
enabled = true
allow_mode_escalation = true
require_approval_on_crisis = true
characterization_complexity = 40
edge_case_complexity = 30
high_refactoring_pressure = 60
high_overengineering_pressure = 60
high_fan_in = 10
high_fan_out = 10
high_centrality = 0.75
```

Thresholds use strict exceedance. Equality does not trigger a rule.

## Rules

- complexity above 30 requires targeted edge-case tests;
- complexity above 40 requires a characterization test before structural rewrite;
- high scoped RP adds `risk-based-testing` and a regression-test requirement;
- high scoped OP adds `architecture-guard` and `engineering-balance`;
- high fan-in or centrality expands contract and component checks;
- high fan-out adds downstream integration checks;
- combined high RP and OP escalates to deep mode and, by default, requires approval;
- unavailable evidence preserves base triage and records uncertainty.

## Artifacts

```text
.agent/state/runs/<run-id>/
├── quality-route.json
└── verification-plan.json
```

Every selected command records a reason and source evidence. Requirements that cannot be mapped to an executable test command remain explicit in `omitted_checks`.

## CLI

```bash
agentkit quality triage --task "Fix session persistence"
agentkit quality plan-checks --task "Fix session persistence"
agentkit quality explain-route --run-id latest
```

## Make

```bash
make ai-quality-triage TASK="Fix session persistence"
make ai-quality-plan TASK="Fix session persistence"
make ai-quality-check TASK="Fix session persistence"
make ai-quality-route QUALITY_ROUTE_RUN_ID=latest
```

The normal `agentkit run` path applies the same routing before implementation, writes the verification plan, and adds the applied route to `completion.json`.
