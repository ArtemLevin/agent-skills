from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Stable AgentKit 1.x process exit codes."""

    SUCCESS = 0
    EMPTY = 1
    ERROR = 2
    APPROVAL_REQUIRED = 3
    NOT_READY = 4
    BUDGET_EXCEEDED = 5
    QUALITY_GATE_FAILED = 6


STABLE_EXIT_CODES = {item.value: item.name.lower() for item in ExitCode}
