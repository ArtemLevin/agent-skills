from __future__ import annotations

import json
import re
from typing import Any

from .models import ReviewFinding, ReviewReport

_JSON_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _candidate_objects(text: str) -> list[str]:
    candidates = [match.group(1) for match in _JSON_FENCE.finditer(text)]
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        candidates.append(text[index : index + end])
    return candidates


def parse_review(text: str) -> ReviewReport:
    payload: dict[str, Any] | None = None
    for candidate in reversed(_candidate_objects(text)):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "verdict" in parsed:
            payload = parsed
            break
    if payload is None:
        return ReviewReport(
            verdict="unstructured",
            findings=[
                ReviewFinding(
                    severity="P1",
                    issue="Review output was not valid structured JSON",
                    evidence="AgentKit cannot prove that blocking findings are absent.",
                    smallest_fix="Run review again with the required JSON contract.",
                )
            ],
            raw_output=text,
        )

    findings: list[ReviewFinding] = []
    for item in payload.get("findings", []):
        if not isinstance(item, dict):
            continue
        findings.append(
            ReviewFinding(
                severity=str(item.get("severity", "P2")).upper(),
                issue=str(item.get("issue", "Unspecified review finding")),
                evidence=str(item.get("evidence", "")),
                smallest_fix=str(item.get("smallest_fix", "")),
                file=str(item.get("file", "")),
            )
        )
    return ReviewReport(verdict=str(payload.get("verdict", "unknown")), findings=findings, raw_output=text)
