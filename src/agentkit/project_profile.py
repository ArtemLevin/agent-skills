from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "shell",
    ".ps1": "powershell",
    ".sql": "sql",
}

_CONTROL_FILES = (
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
    "poetry.lock",
    "Pipfile",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Makefile",
    "Dockerfile",
    "compose.yaml",
    "docker-compose.yml",
)

_EXCLUDED_PARTS = {
    ".git",
    ".agent",
    ".agents",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "vendor",
    "graphify-out",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


@dataclass(frozen=True)
class ProjectProfile:
    version: int
    project_name: str
    generated_at: str
    fingerprint: str
    languages: list[str]
    package_managers: list[str]
    source_roots: list[str]
    test_roots: list[str]
    frameworks: list[str]
    verification_commands: list[list[str]]
    control_files: list[str]
    indexed_files: int
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ProjectProfile":
        return cls(
            version=int(payload["version"]),
            project_name=str(payload["project_name"]),
            generated_at=str(payload["generated_at"]),
            fingerprint=str(payload["fingerprint"]),
            languages=[str(item) for item in payload.get("languages", [])],
            package_managers=[str(item) for item in payload.get("package_managers", [])],
            source_roots=[str(item) for item in payload.get("source_roots", [])],
            test_roots=[str(item) for item in payload.get("test_roots", [])],
            frameworks=[str(item) for item in payload.get("frameworks", [])],
            verification_commands=[
                [str(part) for part in command]
                for command in payload.get("verification_commands", [])
            ],
            control_files=[str(item) for item in payload.get("control_files", [])],
            indexed_files=int(payload.get("indexed_files", 0)),
            truncated=bool(payload.get("truncated", False)),
        )

    def compact(self) -> dict[str, object]:
        return {
            "project_name": self.project_name,
            "fingerprint": self.fingerprint,
            "languages": self.languages,
            "package_managers": self.package_managers,
            "source_roots": self.source_roots,
            "test_roots": self.test_roots,
            "frameworks": self.frameworks,
            "verification_commands": self.verification_commands,
        }


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def list_project_files(
    project_root: Path,
    *,
    max_files: int = 5000,
) -> tuple[list[Path], bool]:
    """Return a deterministic, bounded list of project files.

    Git is preferred because it respects ignore rules. A filesystem walk is used as a fallback.
    """

    command = ["git", "ls-files", "-co", "--exclude-standard", "-z"]
    try:
        result = subprocess.run(
            command,
            cwd=project_root,
            text=False,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        result = None

    paths: list[Path] = []
    if result is not None and result.returncode == 0:
        for raw in result.stdout.split(b"\0"):
            if not raw:
                continue
            relative = raw.decode("utf-8", errors="replace")
            path = project_root / relative
            if path.is_file() and not any(
                part in _EXCLUDED_PARTS for part in path.parts
            ):
                paths.append(path)
    else:
        for path in project_root.rglob("*"):
            if not path.is_file() or any(
                part in _EXCLUDED_PARTS for part in path.parts
            ):
                continue
            paths.append(path)

    unique = sorted(
        {path.resolve() for path in paths},
        key=lambda item: _safe_relative(item, project_root),
    )
    truncated = len(unique) > max_files
    return unique[:max_files], truncated


def _read_small(path: Path, *, limit: int = 512_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _fingerprint(
    project_root: Path,
    files: list[Path],
    control_files: list[Path],
) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: _safe_relative(item, project_root)):
        digest.update(_safe_relative(path, project_root).encode("utf-8"))
        digest.update(b"\0")
    for path in sorted(
        control_files,
        key=lambda item: _safe_relative(item, project_root),
    ):
        digest.update(_safe_relative(path, project_root).encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        except OSError:
            digest.update(b"missing")
    return digest.hexdigest()


def _package_managers(project_root: Path) -> list[str]:
    checks = {
        "uv": ("uv.lock",),
        "poetry": ("poetry.lock",),
        "pip": ("requirements.txt", "pyproject.toml"),
        "pipenv": ("Pipfile",),
        "npm": ("package-lock.json",),
        "pnpm": ("pnpm-lock.yaml",),
        "yarn": ("yarn.lock",),
        "cargo": ("Cargo.toml",),
        "go": ("go.mod",),
        "maven": ("pom.xml",),
        "gradle": ("build.gradle", "build.gradle.kts"),
    }
    return sorted(
        manager
        for manager, filenames in checks.items()
        if any((project_root / filename).is_file() for filename in filenames)
    )


def _frameworks(control_text: str) -> list[str]:
    markers = {
        "django": ("django",),
        "fastapi": ("fastapi",),
        "flask": ("flask",),
        "pyside": ("pyside", "pyqt"),
        "sqlalchemy": ("sqlalchemy",),
        "celery": ("celery",),
        "pytest": ("pytest",),
        "react": ('"react"', " react "),
        "nextjs": ("next",),
        "vue": ("vue",),
        "express": ("express",),
        "spring": ("spring-boot", "org.springframework"),
    }
    lowered = control_text.lower()
    return sorted(
        name
        for name, tokens in markers.items()
        if any(token in lowered for token in tokens)
    )


def _roots(project_root: Path, candidates: tuple[str, ...]) -> list[str]:
    return [name for name in candidates if (project_root / name).is_dir()]


def _verification_commands(
    project_root: Path,
    control_text: str,
) -> list[list[str]]:
    commands: list[list[str]] = []
    tests_exist = any(
        (project_root / name).is_dir() for name in ("tests", "test")
    )
    src_roots = _roots(project_root, ("src", "app", "lib", "tests", "test"))
    if tests_exist:
        if "pytest" in control_text.lower():
            commands.append(["python", "-m", "pytest", "-q"])
        else:
            test_root = "tests" if (project_root / "tests").is_dir() else "test"
            commands.append(
                ["python", "-m", "unittest", "discover", "-s", test_root, "-v"]
            )
    if src_roots and any((project_root / root).exists() for root in src_roots):
        commands.append(["python", "-m", "compileall", "-q", *src_roots])
    if "[tool.ruff" in control_text.lower():
        commands.append(["ruff", "check", "."])
    if (project_root / "package.json").is_file():
        package_text = _read_small(project_root / "package.json")
        if '"test"' in package_text:
            commands.append(["npm", "test", "--", "--runInBand"])
    return commands


def build_project_profile(
    project_root: Path,
    *,
    max_files: int = 5000,
) -> ProjectProfile:
    files, truncated = list_project_files(project_root, max_files=max_files)
    control_paths = [
        project_root / name
        for name in _CONTROL_FILES
        if (project_root / name).is_file()
    ]
    control_text = "\n".join(_read_small(path) for path in control_paths)
    languages = sorted(
        {
            _LANGUAGE_BY_SUFFIX[path.suffix.lower()]
            for path in files
            if path.suffix.lower() in _LANGUAGE_BY_SUFFIX
        }
    )
    return ProjectProfile(
        version=1,
        project_name=project_root.name,
        generated_at=datetime.now(UTC).isoformat(),
        fingerprint=_fingerprint(project_root, files, control_paths),
        languages=languages,
        package_managers=_package_managers(project_root),
        source_roots=_roots(
            project_root,
            ("src", "app", "lib", "packages", "services"),
        ),
        test_roots=_roots(project_root, ("tests", "test", "spec", "__tests__")),
        frameworks=_frameworks(control_text),
        verification_commands=_verification_commands(project_root, control_text),
        control_files=[
            _safe_relative(path, project_root) for path in control_paths
        ],
        indexed_files=len(files),
        truncated=truncated,
    )


def save_project_profile(profile: ProjectProfile, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_project_profile(path: Path) -> ProjectProfile | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return ProjectProfile.from_dict(payload)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def load_or_create_profile(
    project_root: Path,
    profile_path: Path,
    *,
    refresh: bool = False,
    max_files: int = 5000,
) -> tuple[ProjectProfile, bool]:
    existing = None if refresh else load_project_profile(profile_path)
    current = build_project_profile(project_root, max_files=max_files)
    if existing is not None and existing.fingerprint == current.fingerprint:
        return existing, False
    save_project_profile(current, profile_path)
    return current, True
