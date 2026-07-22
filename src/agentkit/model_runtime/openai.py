from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentkit.adapters.base import AgentAdapter
from agentkit.models import CommandResult, TokenUsage

from .base import READ_ONLY_PHASES, REVIEW_OUTPUT_SCHEMA, PromptEnvelope
from .config import ModelTargetConfig

RETRYABLE_RETURN_CODE = 75
CONFIG_RETURN_CODE = 78
SCHEMA_RETURN_CODE = 65

_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}")
_API_KEY = re.compile(r"\b(?:sk|sess)-[A-Za-z0-9_-]{8,}\b")


def _redact(value: object, *secrets: str) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = _BEARER.sub("Bearer [REDACTED]", text)
    return _API_KEY.sub("[REDACTED]", text)


def _value(obj: object, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _usage(response: object) -> TokenUsage:
    usage = _value(response, "usage")
    if usage is None:
        return TokenUsage(measured=False, source="openai.responses.unavailable")
    input_tokens = int(_value(usage, "input_tokens", 0) or 0)
    output_tokens = int(_value(usage, "output_tokens", 0) or 0)
    total_tokens = int(_value(usage, "total_tokens", input_tokens + output_tokens) or 0)
    input_details = _value(usage, "input_tokens_details", {}) or {}
    output_details = _value(usage, "output_tokens_details", {}) or {}
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=int(_value(input_details, "cached_tokens", 0) or 0),
        reasoning_tokens=int(_value(output_details, "reasoning_tokens", 0) or 0),
        total_tokens=total_tokens or input_tokens + output_tokens,
        measured=True,
        source="openai.responses",
    )


def _output_text(response: object) -> str:
    direct = _value(response, "output_text")
    if isinstance(direct, str):
        return direct
    parts: list[str] = []
    output = _value(response, "output", []) or []
    for item in output:
        for content in _value(item, "content", []) or []:
            text = _value(content, "text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _validate_review(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return f"OpenAI review response is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return "OpenAI review response must be a JSON object"
    required = {"verdict", "findings", "criteria_checked", "remaining_risks", "confidence"}
    missing = sorted(required - set(payload))
    if missing:
        return f"OpenAI review response is missing required fields: {missing}"
    if payload.get("verdict") not in {
        "approved",
        "approved_with_non_blocking_findings",
        "changes_required",
    }:
        return "OpenAI review response contains an invalid verdict"
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return "OpenAI review response findings must be an array"
    finding_fields = {"severity", "file", "issue", "evidence", "smallest_fix"}
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict) or set(finding) != finding_fields:
            return f"OpenAI review finding {index} does not match the required fields"
        if finding.get("severity") not in {"P0", "P1", "P2", "P3"}:
            return f"OpenAI review finding {index} contains an invalid severity"
        if not all(isinstance(finding.get(field), str) for field in finding_fields):
            return f"OpenAI review finding {index} fields must be strings"
    criteria = payload.get("criteria_checked")
    if not isinstance(criteria, list) or not all(isinstance(item, str) for item in criteria):
        return "OpenAI review response criteria_checked must be an array"
    remaining = payload.get("remaining_risks")
    if not isinstance(remaining, list) or not all(isinstance(item, str) for item in remaining):
        return "OpenAI review response remaining_risks must be an array"
    if payload.get("confidence") not in {"low", "medium", "high"}:
        return "OpenAI review response contains an invalid confidence"
    return ""


class OpenAIResponsesAdapter(AgentAdapter):
    """Invoke OpenAI Responses for read-only AgentKit phases.

    The adapter never receives local tools, so provider tool calling cannot cross
    AgentKit's local workspace mutation boundary.
    """

    def __init__(
        self,
        target: ModelTargetConfig,
        *,
        client_factory: Callable[..., object] | None = None,
    ) -> None:
        self.target = target
        self.client_factory = client_factory

    def _client(self, api_key: str) -> object:
        if self.client_factory is not None:
            return self.client_factory(
                api_key=api_key,
                timeout=self.target.timeout_seconds,
                max_retries=0,
            )
        from openai import OpenAI  # optional dependency, imported only when selected

        return OpenAI(
            api_key=api_key,
            timeout=self.target.timeout_seconds,
            max_retries=0,
        )

    @staticmethod
    def _error_code(exc: Exception) -> int:
        status = getattr(exc, "status_code", None)
        name = type(exc).__name__.lower()
        if status == 429 or isinstance(status, int) and status >= 500:
            return RETRYABLE_RETURN_CODE
        if "timeout" in name or "connection" in name:
            return RETRYABLE_RETURN_CODE
        if status in {401, 403}:
            return CONFIG_RETURN_CODE
        return 1

    def execute(self, prompt: str, *, phase: str, cwd: Path) -> CommandResult:
        del cwd
        command = ["openai.responses", self.target.model, phase]
        if phase not in READ_ONLY_PHASES:
            return CommandResult(
                command=command,
                returncode=CONFIG_RETURN_CODE,
                stdout="",
                stderr=f"OpenAI direct execution is not allowed for mutating phase '{phase}'",
                duration_seconds=0.0,
                usage=TokenUsage(measured=False, source="openai.responses.not-called"),
            )
        api_key = os.environ.get(self.target.api_key_env, "")
        if not api_key:
            return CommandResult(
                command=command,
                returncode=CONFIG_RETURN_CODE,
                stdout="",
                stderr=f"Environment variable {self.target.api_key_env} is not set",
                duration_seconds=0.0,
                usage=TokenUsage(measured=False, source="openai.responses.not-called"),
            )

        envelope = PromptEnvelope.from_prompt(prompt)
        request: dict[str, Any] = {
            "model": self.target.model,
            "input": prompt,
            "store": self.target.store,
        }
        if self.target.prompt_caching and envelope.stable_prefix:
            request["prompt_cache_key"] = envelope.stable_prefix_hash
        if phase == "review" and self.target.structured_outputs:
            request["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "agentkit_review",
                    "strict": True,
                    "schema": REVIEW_OUTPUT_SCHEMA,
                }
            }
        if self.target.reasoning_effort:
            request["reasoning"] = {"effort": self.target.reasoning_effort}

        started = time.monotonic()
        try:
            client = self._client(api_key)
            response = client.responses.create(**request)
        except ImportError:
            return CommandResult(
                command=command,
                returncode=CONFIG_RETURN_CODE,
                stdout="",
                stderr=(
                    "OpenAI support is not installed; install "
                    "agent-skills-engineering-kit[openai]"
                ),
                duration_seconds=time.monotonic() - started,
                usage=TokenUsage(measured=False, source="openai.responses.not-called"),
            )
        except Exception as exc:  # SDK exception hierarchy is optional at import time
            return CommandResult(
                command=command,
                returncode=self._error_code(exc),
                stdout="",
                stderr=_redact(exc, api_key),
                duration_seconds=time.monotonic() - started,
                usage=TokenUsage(measured=False, source="openai.responses.failed"),
            )

        text = _output_text(response)
        error = ""
        returncode = 0
        if not text.strip():
            error = "OpenAI Responses returned no text output"
            returncode = SCHEMA_RETURN_CODE
        elif phase == "review" and self.target.structured_outputs:
            error = _validate_review(text)
            returncode = SCHEMA_RETURN_CODE if error else 0
        return CommandResult(
            command=command,
            returncode=returncode,
            stdout=text,
            stderr=error,
            duration_seconds=time.monotonic() - started,
            usage=_usage(response),
        )
