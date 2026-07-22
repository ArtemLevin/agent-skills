from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_QUALITY_CI_TOML = r'''

# BEGIN AGENTKIT QUALITY CI
[quality.ci]
enabled = true
workflow_path = ".github/workflows/agentkit-quality.yml"
python_version = "3.11"
base_branch = "main"
package_spec = "agent-skills-engineering-kit[quality]"
artifact_retention_days = 7
cache_enabled = true
annotations = false
eval_smoke_enabled = false
eval_manifest_directory = "evals/tasks"
eval_repetitions = 1
# END AGENTKIT QUALITY CI
'''


@dataclass(frozen=True)
class QualityCIConfig:
    enabled: bool = True
    workflow_path: str = ".github/workflows/agentkit-quality.yml"
    python_version: str = "3.11"
    base_branch: str = "main"
    package_spec: str = "agent-skills-engineering-kit[quality]"
    artifact_retention_days: int = 7
    cache_enabled: bool = True
    annotations: bool = False
    eval_smoke_enabled: bool = False
    eval_manifest_directory: str = "evals/tasks"
    eval_repetitions: int = 1


def _table(value: Any, *, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a table")
    return value


def _safe_relative(value: Any, *, name: str, default: str) -> str:
    raw = str(default if value is None else value).strip()
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{name} must be a project-relative path")
    return path.as_posix()


def load_quality_ci_config(project_root: Path) -> QualityCIConfig:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        return QualityCIConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    quality = _table(data.get("quality"), name="quality")
    ci = _table(quality.get("ci"), name="quality.ci")

    workflow_path = _safe_relative(
        ci.get("workflow_path"),
        name="quality.ci.workflow_path",
        default=".github/workflows/agentkit-quality.yml",
    )
    python_version = str(ci.get("python_version", "3.11")).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", python_version):
        raise ValueError("quality.ci.python_version contains unsupported characters")
    base_branch = str(ci.get("base_branch", "main")).strip()
    if (
        not re.fullmatch(r"[A-Za-z0-9._/-]+", base_branch)
        or ".." in base_branch
        or base_branch.startswith(("/", "."))
        or base_branch.endswith(("/", "."))
    ):
        raise ValueError("quality.ci.base_branch is not a safe branch name")
    package_spec = str(
        ci.get("package_spec", "agent-skills-engineering-kit[quality]")
    ).strip()
    if not package_spec:
        raise ValueError("quality.ci.package_spec must not be empty")
    retention = int(ci.get("artifact_retention_days", 7))
    if retention < 1 or retention > 90:
        raise ValueError(
            "quality.ci.artifact_retention_days must be between 1 and 90"
        )
    eval_repetitions = int(ci.get("eval_repetitions", 1))
    if eval_repetitions < 1 or eval_repetitions > 10:
        raise ValueError("quality.ci.eval_repetitions must be between 1 and 10")

    return QualityCIConfig(
        enabled=bool(ci.get("enabled", True)),
        workflow_path=workflow_path,
        python_version=python_version,
        base_branch=base_branch,
        package_spec=package_spec,
        artifact_retention_days=retention,
        cache_enabled=bool(ci.get("cache_enabled", True)),
        annotations=bool(ci.get("annotations", False)),
        eval_smoke_enabled=bool(ci.get("eval_smoke_enabled", False)),
        eval_manifest_directory=_safe_relative(
            ci.get("eval_manifest_directory"),
            name="quality.ci.eval_manifest_directory",
            default="evals/tasks",
        ),
        eval_repetitions=eval_repetitions,
    )


def ensure_quality_ci_config(project_root: Path) -> Path:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    text = path.read_text(encoding="utf-8")
    if "[quality.ci]" not in text:
        path.write_text(text.rstrip() + DEFAULT_QUALITY_CI_TOML, encoding="utf-8")
        return path
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "[quality.ci]")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break
    section = "\n".join(lines[start:end])
    additions = [
        "eval_smoke_enabled = false",
        'eval_manifest_directory = "evals/tasks"',
        "eval_repetitions = 1",
    ]
    missing = [line for line in additions if line.split(" = ", 1)[0] not in section]
    if missing:
        lines[end:end] = missing
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path
