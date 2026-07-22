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


def _table(value: Any, *, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a table")
    return value


def load_quality_ci_config(project_root: Path) -> QualityCIConfig:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        return QualityCIConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    quality = _table(data.get("quality"), name="quality")
    ci = _table(quality.get("ci"), name="quality.ci")

    workflow_path = str(
        ci.get("workflow_path", ".github/workflows/agentkit-quality.yml")
    ).strip()
    if not workflow_path:
        raise ValueError("quality.ci.workflow_path must not be empty")
    workflow = Path(workflow_path)
    if workflow.is_absolute() or ".." in workflow.parts:
        raise ValueError("quality.ci.workflow_path must be a project-relative path")

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

    return QualityCIConfig(
        enabled=bool(ci.get("enabled", True)),
        workflow_path=workflow_path,
        python_version=python_version,
        base_branch=base_branch,
        package_spec=package_spec,
        artifact_retention_days=retention,
        cache_enabled=bool(ci.get("cache_enabled", True)),
        annotations=bool(ci.get("annotations", False)),
    )


def ensure_quality_ci_config(project_root: Path) -> Path:
    path = project_root / ".agent" / "agentkit.toml"
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    text = path.read_text(encoding="utf-8")
    if "[quality.ci]" not in text:
        path.write_text(text.rstrip() + DEFAULT_QUALITY_CI_TOML, encoding="utf-8")
    return path
