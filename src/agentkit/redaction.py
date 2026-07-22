from __future__ import annotations

import re
from typing import Any

_KEY = re.compile(
    r"(?i)(api[_-]?key|authorization|password|secret|token|credential)"
)
_BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{8,}")
_OPENAI_KEY = re.compile(r"\bsk-[a-zA-Z0-9_-]{8,}\b")
_ASSIGNMENT = re.compile(
    r"(?im)^(\s*[{,]?\s*[\"']?(?:api[_-]?key|authorization|password|secret|token|credential)"
    r"[\"']?\s*[:=]\s*).+$"
)


def redact_text(value: str) -> str:
    value = _ASSIGNMENT.sub(r"\1[REDACTED]", value)
    value = _BEARER.sub("Bearer [REDACTED]", value)
    return _OPENAI_KEY.sub("[REDACTED]", value)


def redact(value: Any, *, key: str = "") -> Any:
    if key and _KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
