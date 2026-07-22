from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from agentkit.models import CommandResult


class AgentAdapter(ABC):
    @abstractmethod
    def execute(self, prompt: str, *, phase: str, cwd: Path) -> CommandResult:
        raise NotImplementedError
