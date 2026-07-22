from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .config import BudgetConfig
from .models import CommandResult, TokenUsage


_TOKEN_ALIASES = {
    "input_tokens": {"inputtokens", "prompttokens", "inputtokencount", "prompttokencount"},
    "output_tokens": {
        "outputtokens",
        "completiontokens",
        "outputtokencount",
        "candidatestokencount",
    },
    "cached_input_tokens": {
        "cachedinputtokens",
        "cachedtokens",
        "cachereadinputtokens",
        "cachereadtokens",
    },
    "reasoning_tokens": {"reasoningtokens", "reasoningtokencount"},
    "total_tokens": {"totaltokens", "totaltokencount"},
}

_REGEX_PATTERNS = {
    "input_tokens": re.compile(r"(?:input|prompt)\s+tokens?\s*[:=]\s*([\d,]+)", re.I),
    "output_tokens": re.compile(r"(?:output|completion)\s+tokens?\s*[:=]\s*([\d,]+)", re.I),
    "cached_input_tokens": re.compile(
        r"(?:cached\s+input|cache(?:d)?\s+read)\s+tokens?\s*[:=]\s*([\d,]+)", re.I
    ),
    "reasoning_tokens": re.compile(r"reasoning\s+tokens?\s*[:=]\s*([\d,]+)", re.I),
    "total_tokens": re.compile(r"total\s+tokens?\s*[:=]\s*([\d,]+)", re.I),
}


def _normalise_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _as_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if cleaned.isdigit():
            return int(cleaned)
    return None


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_dicts(item)


def _usage_from_dict(value: dict[str, Any]) -> TokenUsage | None:
    found: dict[str, int] = {}
    for raw_key, raw_value in value.items():
        key = _normalise_key(str(raw_key))
        for field_name, aliases in _TOKEN_ALIASES.items():
            if key in aliases:
                parsed = _as_non_negative_int(raw_value)
                if parsed is not None:
                    found[field_name] = parsed

    for details_key in ("input_tokens_details", "prompt_tokens_details"):
        details = value.get(details_key)
        if isinstance(details, dict):
            parsed = _as_non_negative_int(details.get("cached_tokens"))
            if parsed is not None:
                found["cached_input_tokens"] = parsed
    for details_key in ("output_tokens_details", "completion_tokens_details"):
        details = value.get(details_key)
        if isinstance(details, dict):
            parsed = _as_non_negative_int(details.get("reasoning_tokens"))
            if parsed is not None:
                found["reasoning_tokens"] = parsed

    if not found:
        return None
    input_tokens = found.get("input_tokens", 0)
    output_tokens = found.get("output_tokens", 0)
    total_tokens = found.get("total_tokens", input_tokens + output_tokens)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=found.get("cached_input_tokens", 0),
        reasoning_tokens=found.get("reasoning_tokens", 0),
        total_tokens=total_tokens,
        measured=True,
        source="json",
    )


def _json_candidates(text: str) -> list[Any]:
    candidates: list[Any] = []
    stripped = text.strip()
    if stripped:
        try:
            candidates.append(json.loads(stripped))
        except json.JSONDecodeError:
            pass
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] not in "[{":
            continue
        try:
            candidates.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return candidates


def parse_token_usage(stdout: str, stderr: str = "") -> TokenUsage:
    """Extract usage from common CLI JSON/text formats without inventing missing tokens."""
    usages: list[TokenUsage] = []
    for payload in _json_candidates(stdout) + _json_candidates(stderr):
        for item in _walk_dicts(payload):
            usage = _usage_from_dict(item)
            if usage is not None:
                usages.append(usage)
    if usages:
        return max(
            usages,
            key=lambda item: (
                int(item.input_tokens > 0)
                + int(item.output_tokens > 0)
                + int(item.cached_input_tokens > 0)
                + int(item.total_tokens > 0),
                item.total_tokens,
            ),
        )

    combined = "\n".join(part for part in (stdout, stderr) if part)
    found: dict[str, int] = {}
    for field_name, pattern in _REGEX_PATTERNS.items():
        matches = pattern.findall(combined)
        if matches:
            found[field_name] = int(matches[-1].replace(",", ""))
    if found:
        input_tokens = found.get("input_tokens", 0)
        output_tokens = found.get("output_tokens", 0)
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=found.get("cached_input_tokens", 0),
            reasoning_tokens=found.get("reasoning_tokens", 0),
            total_tokens=found.get("total_tokens", input_tokens + output_tokens),
            measured=True,
            source="text",
        )
    return TokenUsage(measured=False, source="unavailable")


@dataclass(frozen=True)
class UsageEvent:
    timestamp: str
    phase: str
    kind: str
    provider: str
    executable: str
    returncode: int
    duration_seconds: float
    timed_out: bool
    usage: TokenUsage

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["usage"] = self.usage.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UsageEvent":
        usage = data.get("usage", {})
        return cls(
            timestamp=str(data.get("timestamp", "")),
            phase=str(data.get("phase", "")),
            kind=str(data.get("kind", "tool")),
            provider=str(data.get("provider", "")),
            executable=str(data.get("executable", "")),
            returncode=int(data.get("returncode", 0)),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            timed_out=bool(data.get("timed_out", False)),
            usage=TokenUsage.from_dict(usage if isinstance(usage, dict) else {}),
        )


@dataclass
class UsageLedger:
    run_id: str
    provider: str
    events: list[UsageEvent] = field(default_factory=list)

    def record(
        self,
        *,
        phase: str,
        kind: str,
        result: CommandResult,
        provider: str | None = None,
    ) -> UsageEvent:
        usage = result.usage or TokenUsage(measured=False, source="not-applicable")
        phase = phase.replace("-", "_")
        event = UsageEvent(
            timestamp=datetime.now(UTC).isoformat(),
            phase=phase,
            kind=kind,
            provider=provider or self.provider,
            executable=result.command[0] if result.command else "",
            returncode=result.returncode,
            duration_seconds=result.duration_seconds,
            timed_out=result.timed_out,
            usage=usage,
        )
        self.events.append(event)
        return event

    def phase_totals(self) -> dict[str, dict[str, Any]]:
        phases: dict[str, dict[str, Any]] = {}
        for event in self.events:
            item = phases.setdefault(
                event.phase,
                {
                    "agent_calls": 0,
                    "tool_calls": 0,
                    "duration_seconds": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_input_tokens": 0,
                    "reasoning_tokens": 0,
                    "total_tokens": 0,
                    "measured_agent_calls": 0,
                    "unknown_agent_calls": 0,
                },
            )
            item[f"{event.kind}_calls"] = int(item.get(f"{event.kind}_calls", 0)) + 1
            item["duration_seconds"] += event.duration_seconds
            if event.kind == "agent":
                if event.usage.measured:
                    item["measured_agent_calls"] += 1
                    item["input_tokens"] += event.usage.input_tokens
                    item["output_tokens"] += event.usage.output_tokens
                    item["cached_input_tokens"] += event.usage.cached_input_tokens
                    item["reasoning_tokens"] += event.usage.reasoning_tokens
                    item["total_tokens"] += event.usage.total_tokens
                else:
                    item["unknown_agent_calls"] += 1
        for item in phases.values():
            item["duration_seconds"] = round(float(item["duration_seconds"]), 3)
        return phases

    def totals(self) -> dict[str, Any]:
        totals = {
            "agent_calls": 0,
            "tool_calls": 0,
            "duration_seconds": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "measured_agent_calls": 0,
            "unknown_agent_calls": 0,
        }
        for phase in self.phase_totals().values():
            for key in totals:
                totals[key] += phase[key]
        totals["duration_seconds"] = round(float(totals["duration_seconds"]), 3)
        return totals

    def provider_totals(self) -> dict[str, dict[str, Any]]:
        providers: dict[str, UsageLedger] = {}
        for event in self.events:
            ledger = providers.setdefault(
                event.provider,
                UsageLedger(run_id=self.run_id, provider=event.provider),
            )
            ledger.events.append(event)
        return {name: ledger.totals() for name, ledger in sorted(providers.items())}

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "run_id": self.run_id,
            "provider": self.provider,
            "totals": self.totals(),
            "phases": self.phase_totals(),
            "providers": self.provider_totals(),
            "events": [event.to_dict() for event in self.events],
        }

    def save(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "UsageLedger":
        data = json.loads(path.read_text(encoding="utf-8"))
        ledger = cls(run_id=str(data.get("run_id", path.parent.name)), provider=str(data.get("provider", "")))
        events = data.get("events", [])
        if isinstance(events, list):
            ledger.events = [UsageEvent.from_dict(item) for item in events if isinstance(item, dict)]
        return ledger


@dataclass(frozen=True)
class BudgetStatus:
    enabled: bool
    allowed: bool
    soft_limits_reached: list[str]
    hard_limits_exceeded: list[str]
    unknown_agent_calls: int
    totals: dict[str, Any]
    phase_agent_calls: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BudgetController:
    def __init__(self, config: BudgetConfig) -> None:
        self.config = config

    def evaluate(self, ledger: UsageLedger) -> BudgetStatus:
        totals = ledger.totals()
        phase_calls = {
            phase: int(values.get("agent_calls", 0))
            for phase, values in ledger.phase_totals().items()
        }
        soft: list[str] = []
        hard: list[str] = []

        def reached(name: str, value: float, soft_limit: float, hard_limit: float) -> None:
            if soft_limit > 0 and value >= soft_limit:
                soft.append(f"{name} reached soft limit {soft_limit:g} (current {value:g})")
            if hard_limit > 0 and value > hard_limit:
                hard.append(f"{name} exceeded hard limit {hard_limit:g} (current {value:g})")

        reached("input_tokens", float(totals["input_tokens"]), self.config.soft_input_tokens, self.config.hard_input_tokens)
        reached("output_tokens", float(totals["output_tokens"]), self.config.soft_output_tokens, self.config.hard_output_tokens)
        reached("agent_calls", float(totals["agent_calls"]), self.config.soft_agent_calls, self.config.hard_agent_calls)
        reached(
            "duration_seconds",
            float(totals["duration_seconds"]),
            self.config.soft_duration_seconds,
            self.config.hard_duration_seconds,
        )
        for phase, limit in self.config.phase_agent_call_limits.items():
            current = phase_calls.get(phase, 0)
            if limit > 0 and current > limit:
                hard.append(f"phase {phase} exceeded agent-call limit {limit} (current {current})")
        unknown = int(totals["unknown_agent_calls"])
        if unknown and self.config.unknown_usage_policy == "stop":
            hard.append(f"{unknown} agent call(s) did not expose token usage")
        elif unknown and self.config.unknown_usage_policy == "warn":
            soft.append(f"{unknown} agent call(s) did not expose token usage; token totals are partial")
        return BudgetStatus(
            enabled=self.config.enabled,
            allowed=not self.config.enabled or not hard,
            soft_limits_reached=soft,
            hard_limits_exceeded=hard,
            unknown_agent_calls=unknown,
            totals=totals,
            phase_agent_calls=phase_calls,
        )

    def can_start_agent_call(self, ledger: UsageLedger, phase: str) -> tuple[bool, str]:
        if not self.config.enabled:
            return True, ""
        totals = ledger.totals()
        checks = (
            ("input token", totals["input_tokens"], self.config.hard_input_tokens),
            ("output token", totals["output_tokens"], self.config.hard_output_tokens),
            ("agent call", totals["agent_calls"], self.config.hard_agent_calls),
            ("duration", totals["duration_seconds"], self.config.hard_duration_seconds),
        )
        for name, value, limit in checks:
            if limit > 0 and float(value) >= float(limit):
                return False, f"Cannot start {phase}: {name} hard limit {limit} is already reached"
        normalised_phase = phase.replace("-", "_")
        phase_limit = self.config.phase_agent_call_limits.get(normalised_phase, 0)
        phase_calls = ledger.phase_totals().get(normalised_phase, {}).get("agent_calls", 0)
        if phase_limit > 0 and int(phase_calls) >= phase_limit:
            return False, f"Cannot start {phase}: phase agent-call limit {phase_limit} is reached"
        if self.config.unknown_usage_policy == "stop" and totals["unknown_agent_calls"]:
            return False, "Cannot start another agent call because previous token usage was unavailable"
        return True, ""
