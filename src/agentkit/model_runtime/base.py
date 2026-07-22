from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

DYNAMIC_MARKER = "--- AGENTKIT DYNAMIC CONTEXT ---"
READ_ONLY_PHASES = frozenset({"plan", "review"})
MUTATING_PHASES = frozenset({"implementation", "targeted_fix"})


@dataclass(frozen=True)
class AgentCapabilities:
    structured_outputs: bool = False
    exact_usage: bool = False
    prompt_caching: bool = False
    session_resume: bool = False
    tool_calling: bool = False
    local_workspace_mutation: bool = False
    read_only_mode: bool = True
    reasoning_control: bool = False
    max_context_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PromptEnvelope:
    stable_prefix: str
    dynamic_context: str
    stable_prefix_hash: str

    @classmethod
    def from_prompt(cls, prompt: str) -> PromptEnvelope:
        if DYNAMIC_MARKER in prompt:
            stable, dynamic = prompt.split(DYNAMIC_MARKER, 1)
        else:
            stable, dynamic = "", prompt
        stable = stable.rstrip()
        return cls(
            stable_prefix=stable,
            dynamic_context=dynamic.lstrip(),
            stable_prefix_hash=hashlib.sha256(stable.encode("utf-8")).hexdigest(),
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            "version": 1,
            "stable_prefix_hash": self.stable_prefix_hash,
            "stable_prefix_chars": len(self.stable_prefix),
            "dynamic_context_chars": len(self.dynamic_context),
        }


REVIEW_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "findings", "criteria_checked", "remaining_risks", "confidence"],
    "properties": {
        "verdict": {
            "type": "string",
            "enum": [
                "approved",
                "approved_with_non_blocking_findings",
                "changes_required",
            ],
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "file", "issue", "evidence", "smallest_fix"],
                "properties": {
                    "severity": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                    "file": {"type": "string"},
                    "issue": {"type": "string"},
                    "evidence": {"type": "string"},
                    "smallest_fix": {"type": "string"},
                },
            },
        },
        "criteria_checked": {"type": "array", "items": {"type": "string"}},
        "remaining_risks": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
}
