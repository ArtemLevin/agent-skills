from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from agentkit.commands import CommandPolicy
from agentkit.config import ContextConfig, SecurityConfig
from agentkit.context_cache import ContextCache
from agentkit.models import CommandResult

from .config import QualityConfig
from .errors import QualityProviderExecutionError, QualityProviderParseError
from .models import Availability, QualityProviderStatus, QualitySnapshot
from .parser import PARSER_VERSION
from .strictacode import StrictaCodeProvider

Observer = Callable[[str, CommandResult], None]

_CACHE_NAMESPACE = "quality_snapshot"
_SUPPORTED_SOURCE_SUFFIXES = {
    ".py",
    ".go",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".kt",
    ".kts",
    ".swift",
}
_CONTROL_FILES = {
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    "poetry.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "go.mod",
    "go.sum",
    ".strictacode.yml",
    ".strictacode.yaml",
    ".strictacode.json",
}


@dataclass(frozen=True)
class QualityArtifacts:
    snapshot_path: Path
    hotspots_path: Path
    provider_path: Path
    raw_stdout_path: Path | None = None
    raw_stderr_path: Path | None = None


@dataclass(frozen=True)
class QualityAnalysisResult:
    snapshot: QualitySnapshot
    provider_status: QualityProviderStatus
    artifacts: QualityArtifacts

    @property
    def warning(self) -> str:
        if self.snapshot.usable:
            return ""
        return self.provider_status.message or (
            self.snapshot.warnings[0] if self.snapshot.warnings else "Quality evidence unavailable"
        )


class QualityService:
    def __init__(
        self,
        project_root: Path,
        quality_config: QualityConfig,
        context_config: ContextConfig,
        security_config: SecurityConfig,
        *,
        observer: Observer | None = None,
        phase: str = "quality_before",
    ) -> None:
        self.project_root = project_root
        self.quality_config = quality_config
        self.context_config = context_config
        self.security_config = security_config
        executable_name = Path(quality_config.command[0]).name.lower()
        if executable_name.endswith(".exe"):
            executable_name = executable_name[:-4]
        allowed = list(security_config.allowed_executables)
        if executable_name not in {item.lower().removesuffix(".exe") for item in allowed}:
            allowed.append(executable_name)
        self.policy = CommandPolicy(allowed, security_config.denied_substrings)
        self.provider = StrictaCodeProvider(
            quality_config,
            self.policy,
            observer=observer,
            phase=phase,
        )
        cache_path = Path(context_config.cache_path)
        if not cache_path.is_absolute():
            cache_path = project_root / cache_path
        self.cache = ContextCache(cache_path)

    def doctor(self) -> QualityProviderStatus:
        return self.provider.doctor(self.project_root)

    @staticmethod
    def _normalise_pattern(value: str) -> str:
        return value.strip().replace("\\", "/").strip("/")

    def _is_excluded(self, relative: Path) -> bool:
        posix = relative.as_posix()
        parts = set(relative.parts)
        defaults = {".git", ".agent", "__pycache__", ".pytest_cache", ".mypy_cache"}
        if parts & defaults:
            return True
        for raw in self.quality_config.exclude:
            pattern = self._normalise_pattern(raw)
            if not pattern:
                continue
            if posix == pattern or posix.startswith(pattern + "/") or pattern in relative.parts:
                return True
        return False

    def _is_included(self, relative: Path) -> bool:
        if not self.quality_config.include:
            return True
        posix = relative.as_posix()
        for raw in self.quality_config.include:
            pattern = self._normalise_pattern(raw)
            if posix == pattern or posix.startswith(pattern + "/"):
                return True
        return False

    def _fingerprint(self, *, details: bool, provider_version: str) -> tuple[str, bool, list[str]]:
        digest = hashlib.sha256()
        config_payload = {
            "provider": self.quality_config.provider,
            "provider_version": provider_version,
            "command": self.quality_config.command,
            "details": details,
            "include": self.quality_config.include,
            "exclude": self.quality_config.exclude,
            "limits": {
                "packages": self.quality_config.max_packages,
                "modules": self.quality_config.max_modules,
                "classes": self.quality_config.max_classes,
                "methods": self.quality_config.max_methods,
                "functions": self.quality_config.max_functions,
            },
            "parser_version": PARSER_VERSION,
        }
        encoded_config = json.dumps(
            config_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(encoded_config)
        files: list[Path] = []
        warnings: list[str] = []
        max_files = max(1, self.context_config.max_profile_files)
        truncated = False
        for path in sorted(self.project_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.project_root)
            if self._is_excluded(relative):
                continue
            if (
                path.name not in _CONTROL_FILES
                and path.suffix.lower() not in _SUPPORTED_SOURCE_SUFFIXES
            ):
                continue
            if not self._is_included(relative) and path.name not in _CONTROL_FILES:
                continue
            files.append(path)
            if len(files) > max_files:
                truncated = True
                files = files[:max_files]
                warnings.append(
                    "Source fingerprint exceeded "
                    f"context.max_profile_files={max_files}; quality cache disabled"
                )
                break
        for path in files:
            relative = path.relative_to(self.project_root).as_posix()
            digest.update(relative.encode("utf-8"))
            try:
                digest.update(path.read_bytes())
            except OSError as exc:
                warnings.append(f"Could not hash {relative}: {exc}")
                truncated = True
        return digest.hexdigest(), truncated, warnings

    def _cache_key(self, *, details: bool) -> str:
        payload = {
            "provider": self.quality_config.provider,
            "details": details,
            "include": self.quality_config.include,
            "exclude": self.quality_config.exclude,
            "limits": [
                self.quality_config.max_packages,
                self.quality_config.max_modules,
                self.quality_config.max_classes,
                self.quality_config.max_methods,
                self.quality_config.max_functions,
            ],
            "parser_version": PARSER_VERSION,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _load_cached(self, *, details: bool, fingerprint: str) -> QualitySnapshot | None:
        if not self.quality_config.cache_enabled:
            return None
        entry = self.cache.get(
            _CACHE_NAMESPACE,
            self._cache_key(details=details),
            fingerprint=fingerprint,
        )
        if entry is None:
            return None
        return QualitySnapshot.from_dict(entry.payload).with_runtime(cache_hit=True)

    def _put_cached(self, snapshot: QualitySnapshot, *, details: bool, fingerprint: str) -> None:
        if not self.quality_config.cache_enabled or snapshot.truncated or not snapshot.usable:
            return
        self.cache.put(
            _CACHE_NAMESPACE,
            self._cache_key(details=details),
            fingerprint=fingerprint,
            payload=snapshot.with_runtime(cache_hit=False).to_dict(),
            metadata={
                "provider": snapshot.provider,
                "provider_version": snapshot.provider_version,
                "details": details,
                "generated_at": snapshot.generated_at,
            },
            ttl_seconds=self.quality_config.cache_ttl_seconds,
        )

    @staticmethod
    def _unavailable_snapshot(
        status: QualityProviderStatus,
        *,
        fingerprint: str = "",
        warning: str = "",
    ) -> QualitySnapshot:
        warnings = tuple(item for item in (warning, status.message) if item)
        return QualitySnapshot(
            availability=status.availability,
            provider=status.provider,
            provider_version=status.provider_version,
            source_fingerprint=fingerprint,
            project=None,
            warnings=warnings,
        )

    def _analyze_level(
        self,
        *,
        details: bool,
        provider_status: QualityProviderStatus,
    ) -> QualitySnapshot:
        fingerprint, fingerprint_truncated, fingerprint_warnings = self._fingerprint(
            details=details,
            provider_version=provider_status.provider_version,
        )
        if not fingerprint_truncated:
            cached = self._load_cached(details=details, fingerprint=fingerprint)
            if cached is not None:
                return cached.with_runtime(
                    source_fingerprint=fingerprint,
                    warnings=cached.warnings + tuple(fingerprint_warnings),
                )
        snapshot = self.provider.analyze(
            self.project_root,
            details=details,
            include=self.quality_config.include,
            exclude=self.quality_config.exclude,
        )
        warnings = snapshot.warnings + tuple(fingerprint_warnings)
        if fingerprint_truncated:
            warnings += (
                "Quality snapshot was not cached because its source fingerprint was truncated",
            )
        snapshot = snapshot.with_runtime(
            source_fingerprint=fingerprint,
            cache_hit=False,
            warnings=warnings,
        )
        if fingerprint_truncated and not snapshot.truncated:
            snapshot = replace(snapshot, truncated=True)
        self._put_cached(snapshot, details=details, fingerprint=fingerprint)
        return snapshot

    @staticmethod
    def _write_json(path: Path, payload: Any) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _write_artifacts(
        self,
        run_directory: Path,
        snapshot: QualitySnapshot,
        status: QualityProviderStatus,
        *,
        raw_stdout: str | None = None,
        raw_stderr: str | None = None,
    ) -> QualityArtifacts:
        snapshot_path = self._write_json(run_directory / "quality-before.json", snapshot.to_dict())
        hotspots_path = self._write_json(
            run_directory / "quality-hotspots.json",
            {
                "version": 1,
                "generated_at": datetime.now(UTC).isoformat(),
                "availability": snapshot.availability.value,
                "provider": snapshot.provider,
                "provider_version": snapshot.provider_version,
                "source_fingerprint": snapshot.source_fingerprint,
                "hotspots": [item.to_dict() for item in snapshot.hotspots],
                "warnings": list(snapshot.warnings),
                "truncated": snapshot.truncated,
            },
        )
        provider_path = self._write_json(run_directory / "quality-provider.json", status.to_dict())
        stdout_path: Path | None = None
        stderr_path: Path | None = None
        if raw_stdout is not None:
            stdout_path = run_directory / "quality-raw.stdout.txt"
            stdout_path.write_text(raw_stdout, encoding="utf-8")
        if raw_stderr is not None:
            stderr_path = run_directory / "quality-raw.stderr.txt"
            stderr_path.write_text(raw_stderr, encoding="utf-8")
        return QualityArtifacts(
            snapshot_path=snapshot_path,
            hotspots_path=hotspots_path,
            provider_path=provider_path,
            raw_stdout_path=stdout_path,
            raw_stderr_path=stderr_path,
        )

    def analyze(
        self,
        run_directory: Path,
        *,
        force_details: bool = False,
    ) -> QualityAnalysisResult:
        status = self.doctor()
        if not status.usable:
            snapshot = self._unavailable_snapshot(status)
            artifacts = self._write_artifacts(run_directory, snapshot, status)
            return QualityAnalysisResult(snapshot, status, artifacts)

        raw_stdout: str | None = None
        raw_stderr: str | None = None
        try:
            if force_details or self.quality_config.details_policy == "always":
                snapshot = self._analyze_level(details=True, provider_status=status)
            else:
                snapshot = self._analyze_level(details=False, provider_status=status)
                if (
                    self.quality_config.details_policy == "on_warning"
                    and snapshot.elevated
                    and not snapshot.cache_hit
                ):
                    snapshot = self._analyze_level(details=True, provider_status=status)
                elif self.quality_config.details_policy == "on_warning" and snapshot.elevated:
                    detailed = self._analyze_level(details=True, provider_status=status)
                    snapshot = detailed
        except QualityProviderExecutionError as exc:
            raw_stdout = exc.result.stdout
            raw_stderr = exc.result.stderr
            failed_status = QualityProviderStatus(
                availability=Availability.FAILED,
                provider=status.provider,
                provider_version=status.provider_version,
                executable=status.executable,
                detected_languages=status.detected_languages,
                supported_languages=status.supported_languages,
                message=str(exc),
                capabilities=status.capabilities,
            )
            snapshot = self._unavailable_snapshot(failed_status, warning=str(exc))
            status = failed_status
        except QualityProviderParseError as exc:
            raw_stdout = exc.stdout
            raw_stderr = exc.stderr
            failed_status = QualityProviderStatus(
                availability=Availability.FAILED,
                provider=status.provider,
                provider_version=status.provider_version,
                executable=status.executable,
                detected_languages=status.detected_languages,
                supported_languages=status.supported_languages,
                message=str(exc),
                capabilities=status.capabilities,
            )
            snapshot = self._unavailable_snapshot(failed_status, warning=str(exc))
            status = failed_status

        artifacts = self._write_artifacts(
            run_directory,
            snapshot,
            status,
            raw_stdout=raw_stdout,
            raw_stderr=raw_stderr,
        )
        return QualityAnalysisResult(snapshot, status, artifacts)
