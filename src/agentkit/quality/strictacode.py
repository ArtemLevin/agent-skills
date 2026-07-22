from __future__ import annotations

import importlib.metadata
import shutil
from pathlib import Path
from typing import Callable

from agentkit.commands import CommandPolicy, run_command
from agentkit.models import CommandResult

from .base import QualityProvider
from .config import QualityConfig
from .errors import QualityProviderExecutionError
from .models import (
    Availability,
    QualityCapabilities,
    QualityProviderStatus,
    QualitySnapshot,
)
from .parser import parse_strictacode_json

Observer = Callable[[str, CommandResult], None]


_LANGUAGE_EXTENSIONS = {
    "python": {".py"},
    "golang": {".go"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs"},
    "kotlin": {".kt", ".kts"},
    "swift": {".swift"},
}
_KNOWN_UNSUPPORTED = {
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".rb": "ruby",
    ".php": "php",
}


class StrictaCodeProvider(QualityProvider):
    name = "strictacode"

    def __init__(
        self,
        config: QualityConfig,
        policy: CommandPolicy,
        *,
        observer: Observer | None = None,
        phase: str = "quality_before",
    ) -> None:
        self.config = config
        self.policy = policy
        self.observer = observer
        self.phase = phase
        self._version = self._provider_version()

    def _provider_version(self) -> str:
        try:
            return importlib.metadata.version("strictacode")
        except importlib.metadata.PackageNotFoundError:
            return "unknown"

    def capabilities(self) -> QualityCapabilities:
        return QualityCapabilities(
            supported_languages=tuple(_LANGUAGE_EXTENSIONS),
            line_numbers=False,
            provider_version=self._version,
        )

    @staticmethod
    def _excluded(relative: Path) -> bool:
        ignored = {".git", ".agent", ".venv", "venv", "node_modules"}
        return any(part in ignored for part in relative.parts)

    def _detect_languages(self, project_root: Path) -> tuple[str, ...]:
        counts: dict[str, int] = {}
        unsupported: dict[str, int] = {}
        for path in project_root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(project_root)
            if self._excluded(relative):
                continue
            suffix = path.suffix.lower()
            for language, extensions in _LANGUAGE_EXTENSIONS.items():
                if suffix in extensions:
                    counts[language] = counts.get(language, 0) + 1
                    break
            else:
                if suffix in _KNOWN_UNSUPPORTED:
                    name = _KNOWN_UNSUPPORTED[suffix]
                    unsupported[name] = unsupported.get(name, 0) + 1
        if counts:
            ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            return tuple(name for name, _ in ranked)
        ranked = sorted(unsupported.items(), key=lambda item: (-item[1], item[0]))
        return tuple(name for name, _ in ranked)

    def _executable_available(self) -> bool:
        executable = self.config.command[0]
        path = Path(executable).expanduser()
        if path.is_absolute() or path.parent != Path("."):
            return path.exists()
        return shutil.which(executable) is not None

    def doctor(self, project_root: Path) -> QualityProviderStatus:
        capabilities = self.capabilities()
        detected = self._detect_languages(project_root)
        executable = self.config.command[0]
        if not self.config.enabled:
            return QualityProviderStatus(
                availability=Availability.UNAVAILABLE,
                provider=self.name,
                provider_version=self._version,
                executable=executable,
                detected_languages=detected,
                supported_languages=capabilities.supported_languages,
                message="Quality diagnostics are disabled by configuration",
                capabilities=capabilities,
            )
        if not self._executable_available():
            return QualityProviderStatus(
                availability=Availability.UNAVAILABLE,
                provider=self.name,
                provider_version=self._version,
                executable=executable,
                detected_languages=detected,
                supported_languages=capabilities.supported_languages,
                message=f"Quality provider executable was not found: {executable}",
                capabilities=capabilities,
            )
        if detected and not any(item in capabilities.supported_languages for item in detected):
            return QualityProviderStatus(
                availability=Availability.UNSUPPORTED,
                provider=self.name,
                provider_version=self._version,
                executable=executable,
                detected_languages=detected,
                supported_languages=capabilities.supported_languages,
                message="Detected project languages are not supported by StrictaCode",
                capabilities=capabilities,
            )
        return QualityProviderStatus(
            availability=Availability.AVAILABLE,
            provider=self.name,
            provider_version=self._version,
            executable=executable,
            detected_languages=detected,
            supported_languages=capabilities.supported_languages,
            message="StrictaCode provider is available",
            capabilities=capabilities,
        )

    def _command(self, *, details: bool) -> list[str]:
        command = list(self.config.command)
        command.extend(["analyze", ".", "--format", "json"])
        if details:
            command.append("--details")
        else:
            command.append("--short")
        command.extend(
            [
                "--top-packages",
                str(self.config.max_packages),
                "--top-modules",
                str(self.config.max_modules),
                "--top-classes",
                str(self.config.max_classes),
                "--top-methods",
                str(self.config.max_methods),
                "--top-functions",
                str(self.config.max_functions),
            ]
        )
        return command

    def analyze(
        self,
        project_root: Path,
        *,
        details: bool,
        include: list[str] | None,
        exclude: list[str] | None,
    ) -> QualitySnapshot:
        # StrictaCode reads its own project-root config. AgentKit uses these values
        # for cache scoping and exposes the limitation in documentation.
        del include, exclude
        result = run_command(
            self._command(details=details),
            cwd=project_root,
            timeout_seconds=self.config.timeout_seconds,
            policy=self.policy,
        )
        if self.observer is not None:
            self.observer(self.phase, result)
        if not result.passed:
            raise QualityProviderExecutionError(
                f"StrictaCode analysis failed with exit code {result.returncode}",
                result,
            )
        return parse_strictacode_json(
            result.stdout,
            provider_version=self._version,
            details=details,
            limits={
                "packages": self.config.max_packages,
                "modules": self.config.max_modules,
                "classes": self.config.max_classes,
                "methods": self.config.max_methods,
                "functions": self.config.max_functions,
            },
        )
