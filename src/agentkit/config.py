from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = """# AgentKit project configuration
version = 1

[agent]
platform = "codex"
# The {prompt} placeholder is replaced with the generated task packet.
command = ["codex", "exec", "{prompt}"]
timeout_seconds = 1800

[models]
# Disabled preserves the 0.10 fixed-CLI behavior. Configure routes and targets
# before enabling phase-aware OpenAI execution.
enabled = false
default_route = "standard"
max_retries = 1
max_fallbacks = 1

[graphify]
enabled = true
required = false
directed = true
update_before_task = "changed"
query_budget = 1200
max_initial_queries = 1

[workflow]
default_mode = "auto"
require_clean_tree = true
require_review = true
deep_requires_approval = true
max_fix_iterations = 1

[budget]
enabled = true
soft_input_tokens = 30000
hard_input_tokens = 60000
soft_output_tokens = 8000
hard_output_tokens = 16000
soft_agent_calls = 4
hard_agent_calls = 7
soft_duration_seconds = 1800
hard_duration_seconds = 3600
# allow = record partial totals; warn = record a soft warning; stop = block the next model call
unknown_usage_policy = "warn"

[budget.phase_agent_call_limits]
plan = 3
implementation = 1
review = 3
targeted_fix = 1

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

[verification]
# Each command is an argv array. Empty means AgentKit performs conservative auto-discovery.
commands = []
timeout_seconds = 900

[scope]
max_changed_files = 20

[security]
allowed_executables = [
  "git", "python", "python3", "uv", "pytest", "ruff", "mypy",
  "npm", "pnpm", "yarn", "make", "codex", "claude", "gemini", "aider", "graphify"
]
denied_substrings = [
  "rm -rf /", "git push --force", "git reset --hard", "drop database",
  "truncate table", "format c:", 'del /s /q c:\\'
]
"""


@dataclass(frozen=True)
class AgentConfig:
    platform: str = "codex"
    command: list[str] = field(
        default_factory=lambda: ["codex", "exec", "{prompt}"]
    )
    timeout_seconds: int = 1800


@dataclass(frozen=True)
class GraphifyConfig:
    enabled: bool = True
    required: bool = False
    directed: bool = True
    update_before_task: str = "changed"
    query_budget: int = 1200
    max_initial_queries: int = 1


@dataclass(frozen=True)
class WorkflowConfig:
    default_mode: str = "auto"
    require_clean_tree: bool = True
    require_review: bool = True
    deep_requires_approval: bool = True
    max_fix_iterations: int = 1


@dataclass(frozen=True)
class BudgetConfig:
    enabled: bool = True
    soft_input_tokens: int = 30000
    hard_input_tokens: int = 60000
    soft_output_tokens: int = 8000
    hard_output_tokens: int = 16000
    soft_agent_calls: int = 4
    hard_agent_calls: int = 7
    soft_duration_seconds: int = 1800
    hard_duration_seconds: int = 3600
    unknown_usage_policy: str = "warn"
    phase_agent_call_limits: dict[str, int] = field(
        default_factory=lambda: {
            "plan": 3,
            "implementation": 1,
            "review": 3,
            "targeted_fix": 1,
        }
    )


@dataclass(frozen=True)
class ContextConfig:
    enabled: bool = True
    cache_enabled: bool = True
    cache_path: str = ".agent/cache/context.db"
    profile_path: str = ".agent/project-profile.json"
    max_profile_files: int = 5000
    max_candidate_files: int = 12
    max_symbols_per_file: int = 20
    max_context_chars: int = 16000
    cache_ttl_seconds: int = 604800
    stale_after_days: int = 30


@dataclass(frozen=True)
class VerificationConfig:
    commands: list[list[str]] = field(default_factory=list)
    timeout_seconds: int = 900


@dataclass(frozen=True)
class ScopeConfig:
    max_changed_files: int = 20


@dataclass(frozen=True)
class SecurityConfig:
    allowed_executables: list[str] = field(default_factory=list)
    denied_substrings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentKitConfig:
    agent: AgentConfig
    graphify: GraphifyConfig
    workflow: WorkflowConfig
    budget: BudgetConfig
    context: ContextConfig
    verification: VerificationConfig
    scope: ScopeConfig
    security: SecurityConfig


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    raw = data.get(name, {})
    if not isinstance(raw, dict):
        raise ValueError(f"Configuration section [{name}] must be a table")
    return raw


def _string_list(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"{field_name} must be an array of strings")
    return list(value)


def _command_list(value: Any) -> list[list[str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("verification.commands must be an array")
    commands: list[list[str]] = []
    for index, command in enumerate(value):
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) for part in command)
        ):
            raise ValueError(
                f"verification.commands[{index}] must be a non-empty argv array"
            )
        commands.append(list(command))
    return commands


def _positive_int_map(value: Any, *, field_name: str) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a table")
    result: dict[str, int] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).replace("-", "_")
        parsed = int(raw_value)
        if parsed < 0:
            raise ValueError(f"{field_name}.{key} must be zero or positive")
        result[key] = parsed
    return result


def _non_negative_int(
    value: Any,
    *,
    field_name: str,
    default: int,
) -> int:
    parsed = int(default if value is None else value)
    if parsed < 0:
        raise ValueError(f"{field_name} must be zero or positive")
    return parsed


def load_config(project_root: Path) -> AgentKitConfig:
    config_path = project_root / ".agent" / "agentkit.toml"
    if not config_path.is_file():
        raise FileNotFoundError(
            f"{config_path} does not exist. Run 'agentkit init' in the project first."
        )
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    agent = _section(data, "agent")
    graphify = _section(data, "graphify")
    workflow = _section(data, "workflow")
    budget = _section(data, "budget")
    context = _section(data, "context")
    verification = _section(data, "verification")
    scope = _section(data, "scope")
    security = _section(data, "security")

    unknown_usage_policy = str(
        budget.get("unknown_usage_policy", "warn")
    ).lower()
    if unknown_usage_policy not in {"allow", "warn", "stop"}:
        raise ValueError(
            "budget.unknown_usage_policy must be allow, warn, or stop"
        )

    return AgentKitConfig(
        agent=AgentConfig(
            platform=str(agent.get("platform", "codex")),
            command=_string_list(
                agent.get("command", ["codex", "exec", "{prompt}"]),
                field_name="agent.command",
            ),
            timeout_seconds=int(agent.get("timeout_seconds", 1800)),
        ),
        graphify=GraphifyConfig(
            enabled=bool(graphify.get("enabled", True)),
            required=bool(graphify.get("required", False)),
            directed=bool(graphify.get("directed", True)),
            update_before_task=str(
                graphify.get("update_before_task", "changed")
            ),
            query_budget=int(graphify.get("query_budget", 1200)),
            max_initial_queries=int(graphify.get("max_initial_queries", 1)),
        ),
        workflow=WorkflowConfig(
            default_mode=str(workflow.get("default_mode", "auto")),
            require_clean_tree=bool(
                workflow.get("require_clean_tree", True)
            ),
            require_review=bool(workflow.get("require_review", True)),
            deep_requires_approval=bool(
                workflow.get("deep_requires_approval", True)
            ),
            max_fix_iterations=int(
                workflow.get("max_fix_iterations", 1)
            ),
        ),
        budget=BudgetConfig(
            enabled=bool(budget.get("enabled", True)),
            soft_input_tokens=int(
                budget.get("soft_input_tokens", 30000)
            ),
            hard_input_tokens=int(
                budget.get("hard_input_tokens", 60000)
            ),
            soft_output_tokens=int(
                budget.get("soft_output_tokens", 8000)
            ),
            hard_output_tokens=int(
                budget.get("hard_output_tokens", 16000)
            ),
            soft_agent_calls=int(
                budget.get("soft_agent_calls", 4)
            ),
            hard_agent_calls=int(
                budget.get("hard_agent_calls", 7)
            ),
            soft_duration_seconds=int(
                budget.get("soft_duration_seconds", 1800)
            ),
            hard_duration_seconds=int(
                budget.get("hard_duration_seconds", 3600)
            ),
            unknown_usage_policy=unknown_usage_policy,
            phase_agent_call_limits=_positive_int_map(
                budget.get(
                    "phase_agent_call_limits",
                    {
                        "plan": 1,
                        "implementation": 1,
                        "review": 2,
                        "targeted_fix": 1,
                    },
                ),
                field_name="budget.phase_agent_call_limits",
            ),
        ),
        context=ContextConfig(
            enabled=bool(context.get("enabled", True)),
            cache_enabled=bool(context.get("cache_enabled", True)),
            cache_path=str(
                context.get("cache_path", ".agent/cache/context.db")
            ),
            profile_path=str(
                context.get(
                    "profile_path",
                    ".agent/project-profile.json",
                )
            ),
            max_profile_files=_non_negative_int(
                context.get("max_profile_files"),
                field_name="context.max_profile_files",
                default=5000,
            ),
            max_candidate_files=_non_negative_int(
                context.get("max_candidate_files"),
                field_name="context.max_candidate_files",
                default=12,
            ),
            max_symbols_per_file=_non_negative_int(
                context.get("max_symbols_per_file"),
                field_name="context.max_symbols_per_file",
                default=20,
            ),
            max_context_chars=_non_negative_int(
                context.get("max_context_chars"),
                field_name="context.max_context_chars",
                default=16000,
            ),
            cache_ttl_seconds=_non_negative_int(
                context.get("cache_ttl_seconds"),
                field_name="context.cache_ttl_seconds",
                default=604800,
            ),
            stale_after_days=_non_negative_int(
                context.get("stale_after_days"),
                field_name="context.stale_after_days",
                default=30,
            ),
        ),
        verification=VerificationConfig(
            commands=_command_list(verification.get("commands", [])),
            timeout_seconds=int(
                verification.get("timeout_seconds", 900)
            ),
        ),
        scope=ScopeConfig(
            max_changed_files=int(scope.get("max_changed_files", 20))
        ),
        security=SecurityConfig(
            allowed_executables=_string_list(
                security.get("allowed_executables", []),
                field_name="security.allowed_executables",
            ),
            denied_substrings=_string_list(
                security.get("denied_substrings", []),
                field_name="security.denied_substrings",
            ),
        ),
    )


def write_default_config(
    project_root: Path,
    *,
    force: bool = False,
) -> Path:
    config_path = project_root / ".agent" / "agentkit.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists() and not force:
        return config_path
    config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return config_path


def configured_project_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_root = os.environ.get("AGENTKIT_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path.cwd().resolve()
