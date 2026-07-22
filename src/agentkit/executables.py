from __future__ import annotations

import importlib.metadata
import os
import shutil
import sys
import sysconfig
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


PathLookup = Callable[[str], str | None]


@dataclass(frozen=True)
class ExecutableResolution:
    name: str
    path: Path | None
    source: str
    package: str = ""
    package_version: str = ""

    @property
    def found(self) -> bool:
        return self.path is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "found": self.found,
            "path": str(self.path) if self.path else "",
            "source": self.source,
            "package": self.package,
            "package_version": self.package_version,
        }


def _package_version(package_name: str | None) -> str:
    if not package_name:
        return ""
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _candidate_names(name: str) -> tuple[str, ...]:
    names = [name]
    if not name.lower().endswith(".exe"):
        names.append(f"{name}.exe")
    if os.name == "nt":
        names.extend((f"{name}.cmd", f"{name}.bat"))
    return tuple(dict.fromkeys(names))


def _default_candidate_directories() -> tuple[Path, ...]:
    raw = [
        Path(sysconfig.get_path("scripts")),
        Path(sys.executable).resolve().parent,
        Path(sys.executable).parent,
        Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin"),
    ]
    resolved: list[Path] = []
    for directory in raw:
        try:
            candidate = directory.expanduser().resolve()
        except OSError:
            candidate = directory.expanduser()
        if candidate not in resolved:
            resolved.append(candidate)
    return tuple(resolved)


def resolve_executable(
    name: str,
    *,
    package_name: str | None = None,
    path_lookup: PathLookup | None = None,
    candidate_directories: Iterable[Path] | None = None,
) -> ExecutableResolution:
    """Resolve a CLI from PATH or from AgentKit's own Python tool environment."""

    normalized = name.strip()
    if not normalized:
        raise ValueError("Executable name must not be empty")
    package_version = _package_version(package_name)
    lookup = path_lookup or shutil.which
    path_hit = lookup(normalized)
    if path_hit:
        return ExecutableResolution(
            name=normalized,
            path=Path(path_hit).expanduser().resolve(),
            source="path",
            package=package_name or "",
            package_version=package_version,
        )

    directories = (
        tuple(candidate_directories)
        if candidate_directories is not None
        else _default_candidate_directories()
    )
    for directory in directories:
        for candidate_name in _candidate_names(normalized):
            candidate = Path(directory).expanduser() / candidate_name
            if candidate.is_file():
                return ExecutableResolution(
                    name=normalized,
                    path=candidate.resolve(),
                    source="agentkit_tool_environment",
                    package=package_name or "",
                    package_version=package_version,
                )

    return ExecutableResolution(
        name=normalized,
        path=None,
        source="unavailable",
        package=package_name or "",
        package_version=package_version,
    )


def resolve_graphify_executable() -> ExecutableResolution:
    return resolve_executable("graphify", package_name="graphifyy")
