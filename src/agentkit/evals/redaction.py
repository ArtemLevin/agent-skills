from __future__ import annotations

import re
from typing import Any

_SECRET_KEY = re.compile(r"(?:secret|token|password|api[_-]?key|authorization|cookie)", re.I)
_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
)


def redact_text(value: str) -> str:
    result = value
    for pattern in _PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def redact(value: Any, *, key: str = "") -> Any:
    if key and _SECRET_KEY.search(key):
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


def bounded_tail(value: str, limit: int = 2000) -> str:
    text = redact_text(value)
    if len(text) <= limit:
        return text
    return "[...truncated...]\n" + text[-limit:]
