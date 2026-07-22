from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import QualityCapabilities, QualityProviderStatus, QualitySnapshot


class QualityProvider(Protocol):
    name: str

    def capabilities(self) -> QualityCapabilities: ...

    def doctor(self, project_root: Path) -> QualityProviderStatus: ...

    def analyze(
        self,
        project_root: Path,
        *,
        details: bool,
        include: list[str] | None,
        exclude: list[str] | None,
    ) -> QualitySnapshot: ...
