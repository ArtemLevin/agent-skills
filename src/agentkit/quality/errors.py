from __future__ import annotations

from dataclasses import dataclass

from agentkit.models import CommandResult


class QualityError(RuntimeError):
    """Base error for quality diagnostics failures."""


@dataclass
class QualityProviderExecutionError(QualityError):
    message: str
    result: CommandResult

    def __str__(self) -> str:
        return self.message


@dataclass
class QualityProviderParseError(QualityError):
    message: str
    stdout: str
    stderr: str = ""

    def __str__(self) -> str:
        return self.message
