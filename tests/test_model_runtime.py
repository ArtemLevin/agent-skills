from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentkit.adapters import AgentAdapter
from agentkit.config import AgentConfig, BudgetConfig, load_config, write_default_config
from agentkit.graphify import GraphContext
from agentkit.model_runtime.base import REVIEW_OUTPUT_SCHEMA, PromptEnvelope
from agentkit.model_runtime.cli import models_main, providers_main
from agentkit.model_runtime.config import (
    ModelRuntimeConfig,
    ModelTargetConfig,
    load_model_runtime_config,
)
from agentkit.model_runtime.integration import ModelRoutingRunner
from agentkit.model_runtime.openai import (
    CONFIG_RETURN_CODE,
    RETRYABLE_RETURN_CODE,
    SCHEMA_RETURN_CODE,
    OpenAIResponsesAdapter,
)
from agentkit.model_runtime.router import build_route_plan
from agentkit.models import CommandResult, RunMode, Stage, TokenUsage, TriageResult
from agentkit.prompts import implementation_prompt
from agentkit.runner import RunRequest
from agentkit.state import RunState
from agentkit.telemetry import BudgetController, UsageLedger


class FakeAdapter(AgentAdapter):
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = results
        self.calls: list[str] = []

    def execute(self, prompt: str, *, phase: str, cwd: Path) -> CommandResult:
        del prompt, cwd
        self.calls.append(phase)
        return self.results.pop(0)


class MutatingAdapter(AgentAdapter):
    def execute(self, prompt: str, *, phase: str, cwd: Path) -> CommandResult:
        del prompt, phase
        (cwd / "unexpected.txt").write_text("mutation", encoding="utf-8")
        return result(0, "plan")


class FakeResponses:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[dict[str, object]] = []

    def create(self, **request: object) -> object:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def result(returncode: int, output: str = "") -> CommandResult:
    return CommandResult(
        ["fake"],
        returncode,
        output,
        "",
        0.01,
        usage=TokenUsage(input_tokens=2, output_tokens=1, total_tokens=3, measured=True),
    )


class ModelRuntimeConfigTests(unittest.TestCase):
    def test_loads_openai_targets_without_reading_secret_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".agent").mkdir()
            (root / ".agent/agentkit.toml").write_text(
                """
[models]
enabled = true
default_route = "standard"

[models.targets.plan]
provider = "openai"
model = "configured-model"
api_key_env = "OPENAI_API_KEY"

[models.routes.standard]
plan = "plan"
implementation = "legacy-cli"
review = "plan"
targeted_fix = "legacy-cli"
""",
                encoding="utf-8",
            )
            config = load_model_runtime_config(root, AgentConfig())
            self.assertTrue(config.enabled)
            self.assertEqual(config.targets["plan"].model, "configured-model")
            self.assertFalse(hasattr(config.targets["plan"], "api_key"))

    def test_rejects_unknown_provider_and_invalid_environment_name(self) -> None:
        cases = (
            'provider = "anthropic"\nmodel = "x"',
            'provider = "openai"\nmodel = "x"\napi_key_env = "actual-secret-value"',
        )
        for target in cases:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".agent").mkdir()
                (root / ".agent/agentkit.toml").write_text(
                    f"[models]\nenabled = true\n[models.targets.bad]\n{target}\n",
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    load_model_runtime_config(root, AgentConfig())

    def test_rejects_string_false_for_storage_instead_of_enabling_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".agent").mkdir()
            (root / ".agent/agentkit.toml").write_text(
                """
[models]
enabled = true
[models.targets.bad]
provider = "openai"
model = "configured"
store = "false"
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "store must be a boolean"):
                load_model_runtime_config(root, AgentConfig())


class ModelRuntimeCliTests(unittest.TestCase):
    def _project(self, root: Path) -> None:
        write_default_config(root)
        path = root / ".agent/agentkit.toml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("enabled = false", "enabled = true", 1)
            + """

[models.targets.api]
provider = "openai"
model = "configured-model"

[models.routes.standard]
plan = "api"
implementation = "legacy-cli"
review = "api"
targeted_fix = "legacy-cli"
""",
            encoding="utf-8",
        )

    def test_diagnostics_and_route_explanation_do_not_make_paid_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    models_main(["--project-root", str(root), "doctor"]),
                    0,
                )
            self.assertFalse(json.loads(output.getvalue())["paid_request_performed"])

            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    providers_main(["--project-root", str(root), "list"]),
                    0,
                )
            self.assertEqual(
                json.loads(output.getvalue())["supported_providers"],
                ["cli", "openai"],
            )

            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    providers_main(
                        ["--project-root", str(root), "test", "openai", "--target", "api"]
                    ),
                    0,
                )
            self.assertFalse(json.loads(output.getvalue())["paid_request_performed"])

            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    models_main(
                        [
                            "--project-root",
                            str(root),
                            "route",
                            "--task",
                            "Plan a small feature",
                            "--mode",
                            "standard",
                            "--explain",
                        ]
                    ),
                    0,
                )
            route = json.loads(output.getvalue())
            self.assertEqual(route["phases"]["plan"]["target"], "api")


class ModelRouterTests(unittest.TestCase):
    def test_rejects_direct_api_for_mutating_phase(self) -> None:
        openai = ModelTargetConfig(name="api", provider="openai", model="configured")
        local = ModelTargetConfig(name="local", provider="cli", command=("codex",))
        config = ModelRuntimeConfig(
            enabled=True,
            routes={
                "standard": {
                    "plan": "api",
                    "implementation": "api",
                    "review": "api",
                    "targeted_fix": "local",
                }
            },
            targets={"api": openai, "local": local},
        )
        with self.assertRaisesRegex(ValueError, "cannot mutate"):
            build_route_plan(config, mode=RunMode.STANDARD, route_override=None)

    def test_route_is_phase_specific_and_fallback_is_bounded(self) -> None:
        targets = {
            "local": ModelTargetConfig(name="local", provider="cli", command=("codex",)),
            "api": ModelTargetConfig(
                name="api",
                provider="openai",
                model="configured",
                structured_outputs=True,
            ),
        }
        config = ModelRuntimeConfig(
            enabled=True,
            max_fallbacks=1,
            routes={
                "standard": {
                    "plan": "api",
                    "implementation": "local",
                    "review": "api",
                    "targeted_fix": "local",
                }
            },
            targets=targets,
            fallbacks={"plan": ("local", "api")},
        )
        plan = build_route_plan(config, mode=RunMode.STANDARD, route_override=None)
        self.assertEqual(plan.phases["plan"].provider, "openai")
        self.assertEqual(plan.phases["implementation"].provider, "cli")
        self.assertEqual(plan.phases["plan"].fallbacks, ("local",))

        fallback_route = build_route_plan(
            config,
            mode=RunMode.FAST,
            route_override=None,
        )
        self.assertEqual(fallback_route.route, "standard")

    def test_plan_prompt_embeds_contract_before_dynamic_task_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / ".agent/skills/model-routing/SKILL.md"
            skill.parent.mkdir(parents=True)
            (root / ".agent/AGENT.md").write_text("GLOBAL CONTRACT", encoding="utf-8")
            skill.write_text("ROUTING CONTRACT", encoding="utf-8")
            prompt = implementation_prompt(
                project_root=root,
                task="SECRET TASK TEXT",
                triage=TriageResult(
                    RunMode.STANDARD,
                    [],
                    ["model-routing"],
                ),
                graph=GraphContext(False, False, "", "", "skipped"),
                plan_only=True,
            )
            envelope = PromptEnvelope.from_prompt(prompt)
            self.assertIn("GLOBAL CONTRACT", envelope.stable_prefix)
            self.assertIn("ROUTING CONTRACT", envelope.stable_prefix)
            self.assertNotIn("SECRET TASK TEXT", envelope.stable_prefix)
            self.assertIn("SECRET TASK TEXT", envelope.dynamic_context)


class OpenAIAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = ModelTargetConfig(
            name="review",
            provider="openai",
            model="configured-model",
            store=False,
            structured_outputs=True,
            prompt_caching=True,
            reasoning_effort="medium",
        )

    def test_maps_response_usage_and_structured_review_request(self) -> None:
        review = json.dumps(
            {
                "verdict": "approved",
                "findings": [],
                "criteria_checked": ["tests"],
                "remaining_risks": [],
                "confidence": "high",
            }
        )
        response = SimpleNamespace(
            output_text=review,
            usage=SimpleNamespace(
                input_tokens=120,
                output_tokens=30,
                total_tokens=150,
                input_tokens_details=SimpleNamespace(cached_tokens=80),
                output_tokens_details=SimpleNamespace(reasoning_tokens=12),
            ),
        )
        responses = FakeResponses(response=response)
        adapter = OpenAIResponsesAdapter(
            self.target,
            client_factory=lambda **kwargs: FakeClient(responses),
        )
        prompt = "stable contract\n\n--- AGENTKIT DYNAMIC CONTEXT ---\ntask"
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            executed = adapter.execute(prompt, phase="review", cwd=Path.cwd())
        self.assertTrue(executed.passed)
        self.assertEqual(executed.usage.cached_input_tokens, 80)
        self.assertEqual(executed.usage.reasoning_tokens, 12)
        request = responses.requests[0]
        self.assertFalse(request["store"])
        self.assertEqual(
            request["prompt_cache_key"],
            PromptEnvelope.from_prompt(prompt).stable_prefix_hash,
        )
        self.assertEqual(request["text"]["format"]["schema"], REVIEW_OUTPUT_SCHEMA)
        self.assertEqual(request["reasoning"], {"effort": "medium"})

    def test_schema_failure_and_missing_key_fail_closed(self) -> None:
        responses = FakeResponses(response=SimpleNamespace(output_text="{}", usage=None))
        adapter = OpenAIResponsesAdapter(
            self.target,
            client_factory=lambda **kwargs: FakeClient(responses),
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            invalid = adapter.execute("prompt", phase="review", cwd=Path.cwd())
        self.assertEqual(invalid.returncode, SCHEMA_RETURN_CODE)
        with patch.dict(os.environ, {}, clear=True):
            missing = adapter.execute("prompt", phase="plan", cwd=Path.cwd())
        self.assertEqual(missing.returncode, CONFIG_RETURN_CODE)
        self.assertEqual(responses.requests.__len__(), 1)

    def test_adapter_refuses_mutating_phase_before_api_call(self) -> None:
        responses = FakeResponses(response=SimpleNamespace(output_text="unused", usage=None))
        adapter = OpenAIResponsesAdapter(
            self.target,
            client_factory=lambda **kwargs: FakeClient(responses),
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            executed = adapter.execute("prompt", phase="implementation", cwd=Path.cwd())
        self.assertEqual(executed.returncode, CONFIG_RETURN_CODE)
        self.assertEqual(responses.requests, [])

    def test_transient_error_is_retryable_and_secret_is_redacted(self) -> None:
        error = RuntimeError("Bearer secret-token-value sk-secretvalue")
        error.status_code = 429
        responses = FakeResponses(error=error)
        adapter = OpenAIResponsesAdapter(
            self.target,
            client_factory=lambda **kwargs: FakeClient(responses),
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            executed = adapter.execute("prompt", phase="plan", cwd=Path.cwd())
        self.assertEqual(executed.returncode, RETRYABLE_RETURN_CODE)
        self.assertNotIn("secret-token-value", executed.stderr)
        self.assertNotIn("sk-secretvalue", executed.stderr)


class ModelRoutingIntegrationTests(unittest.TestCase):
    def _git_project(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        (root / "README.md").write_text("test", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)

    def test_plan_retries_once_then_uses_single_cli_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git_project(root)
            write_default_config(root)
            path = root / ".agent/agentkit.toml"
            path.write_text(
                path.read_text(encoding="utf-8")
                .replace("enabled = false", "enabled = true", 1)
                .replace("require_clean_tree = true", "require_clean_tree = false")
                + """

[models.targets.api]
provider = "openai"
model = "configured-model"

[models.routes.standard]
plan = "api"
implementation = "legacy-cli"
review = "api"
targeted_fix = "legacy-cli"

[models.fallback]
plan = ["legacy-cli"]
""",
                encoding="utf-8",
            )
            api = FakeAdapter([result(RETRYABLE_RETURN_CODE), result(RETRYABLE_RETURN_CODE)])
            local = FakeAdapter([result(0, "fallback plan")])
            runner = ModelRoutingRunner(
                root,
                config=load_config(root),
                adapter_factories={
                    "openai": lambda target: api,
                    "cli": lambda target: local,
                },
            )
            outcome = runner.run(
                RunRequest(
                    task="Plan a small feature",
                    mode=RunMode.STANDARD,
                    plan_only=True,
                    skip_graph=True,
                )
            )
            self.assertEqual(outcome.stage, Stage.COMPLETE)
            run = root / ".agent/state/runs" / outcome.run_id
            attempts = json.loads((run / "model-attempts.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [item["kind"] for item in attempts["attempts"]],
                ["primary", "retry", "fallback"],
            )
            self.assertEqual(len(api.calls), 2)
            self.assertEqual(len(local.calls), 1)
            usage = json.loads((run / "usage.json").read_text(encoding="utf-8"))
            self.assertEqual(usage["providers"]["openai"]["agent_calls"], 2)
            self.assertEqual(usage["providers"]["cli"]["agent_calls"], 1)

    def test_disabled_models_do_not_break_legacy_runner_with_inactive_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_default_config(root)
            path = root / ".agent/agentkit.toml"
            path.write_text(
                path.read_text(encoding="utf-8")
                + """

[models.targets.inactive]
provider = "unsupported"
""",
                encoding="utf-8",
            )
            runner = ModelRoutingRunner(root, config=load_config(root))
            provider = runner._ledger_provider(
                RunRequest(task="legacy", agent_override=None, route_override=None)
            )
            self.assertEqual(provider, "codex")

    def test_mutating_phase_never_retries_or_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_default_config(root)
            runner = ModelRoutingRunner(root, config=load_config(root))
            local = ModelTargetConfig(name="local", provider="cli", command=("codex",))
            config = ModelRuntimeConfig(
                enabled=True,
                max_retries=3,
                max_fallbacks=1,
                routes={
                    "standard": {
                        "plan": "local",
                        "implementation": "local",
                        "review": "local",
                        "targeted_fix": "local",
                    }
                },
                targets={"local": local},
                fallbacks={"implementation": ("local",)},
            )
            runner._model_config = config
            runner._model_plan = build_route_plan(
                config,
                mode=RunMode.STANDARD,
                route_override=None,
            )
            adapter = FakeAdapter([result(RETRYABLE_RETURN_CODE), result(0)])
            state = RunState(root)
            ledger = UsageLedger(run_id=state.run_id, provider="phase-routed")
            executed, _, _ = runner._execute_agent(
                adapter=adapter,
                prompt="implementation prompt",
                phase="implementation",
                state=state,
                ledger=ledger,
                controller=BudgetController(BudgetConfig()),
                provider="cli",
            )
            self.assertEqual(executed.returncode, RETRYABLE_RETURN_CODE)
            self.assertEqual(adapter.calls, ["implementation"])
            attempts = json.loads(
                (state.directory / "model-attempts.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(attempts["attempts"]), 1)

    def test_plan_cli_fallback_is_checked_for_workspace_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git_project(root)
            write_default_config(root)
            path = root / ".agent/agentkit.toml"
            path.write_text(
                path.read_text(encoding="utf-8")
                .replace("enabled = false", "enabled = true", 1)
                .replace("require_clean_tree = true", "require_clean_tree = false")
                + """

[models.targets.api]
provider = "openai"
model = "configured-model"

[models.routes.standard]
plan = "api"
implementation = "legacy-cli"
review = "api"
targeted_fix = "legacy-cli"

[models.fallback]
plan = ["legacy-cli"]
""",
                encoding="utf-8",
            )
            runner = ModelRoutingRunner(
                root,
                config=load_config(root),
                adapter_factories={
                    "openai": lambda target: FakeAdapter([result(1)]),
                    "cli": lambda target: MutatingAdapter(),
                },
            )
            outcome = runner.run(
                RunRequest(
                    task="Plan a small feature",
                    mode=RunMode.STANDARD,
                    plan_only=True,
                    skip_graph=True,
                )
            )
            self.assertEqual(outcome.stage, Stage.FAILED)
            self.assertIn("modified the working tree", outcome.message)


if __name__ == "__main__":
    unittest.main()
