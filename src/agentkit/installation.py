from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import (
    INSTALLATION_MANIFEST_VERSION,
    MIGRATION_REPORT_VERSION,
    PACKAGE_VERSION,
)

_VOLATILE_PREFIXES = (
    "state/",
    "cache/",
    "evals/",
    "diagnostics/",
    "backups/",
    "update-candidates/",
)

SUPPORTED_UPGRADE_VERSIONS = (
    "0.4.0",
    "0.5.0",
    "0.6.0",
    "0.7.0",
    "0.8.0",
    "0.9.0",
    "0.10.0",
    "0.11.0",
)

_LEGACY_MARKERS = (
    ("0.11.0", "schemas/model-route.schema.json"),
    ("0.10.0", "schemas/eval-run.schema.json"),
    ("0.9.0", "schemas/quality-ci-result.schema.json"),
    ("0.8.0", "schemas/verification-plan.schema.json"),
    ("0.7.0", "schemas/hotspot-context.schema.json"),
    ("0.6.0", "schemas/quality-gate.schema.json"),
    ("0.5.0", "schemas/quality-snapshot.schema.json"),
    ("0.4.0", "schemas/compiled-context.schema.json"),
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _digest(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _strategy(relative: str) -> str:
    if relative == "agentkit.toml":
        return "semantic-config"
    if relative == "Makefile.agent":
        return "managed-blocks"
    if relative == "AGENT.md":
        return "user-owned"
    return "managed-file"


def _managed_files(project_root: Path) -> list[Path]:
    agent = project_root / ".agent"
    if not agent.is_dir():
        return []
    result: list[Path] = []
    for path in sorted(agent.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(agent).as_posix()
        if relative == "installation.json" or relative.startswith(_VOLATILE_PREFIXES):
            continue
        result.append(path)
    return result


def installation_manifest(project_root: Path) -> dict[str, Any] | None:
    path = project_root / ".agent" / "installation.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(".agent/installation.json must contain an object")
    return payload


def detect_legacy_version(project_root: Path) -> str:
    root = project_root / ".agent"
    for version, marker in _LEGACY_MARKERS:
        if (root / marker).is_file():
            return version
    return "unsupported-pre-0.4"


def record_installation_manifest(
    project_root: Path,
    *,
    overwrite: bool = False,
    previous_version: str = "",
) -> Path:
    path = project_root / ".agent" / "installation.json"
    if path.exists() and not overwrite:
        return path
    resources = []
    for item in _managed_files(project_root):
        relative = item.relative_to(project_root / ".agent").as_posix()
        resources.append(
            {
                "path": relative,
                "sha256": _digest(item),
                "strategy": _strategy(relative),
            }
        )
    payload = {
        "version": INSTALLATION_MANIFEST_VERSION,
        "agentkit_version": PACKAGE_VERSION,
        "previous_version": previous_version,
        "installed_at": _now(),
        "resources": resources,
    }
    _atomic_json(path, payload)
    return path


def _source_resources() -> dict[str, bytes]:
    from .init_project import _source_kit_root

    source = _source_kit_root()
    if source is None:
        return {}
    result: dict[str, bytes] = {"AGENT.md": (source / "AGENT.md").read_bytes()}
    for directory in ("skills", "policies", "schemas", "templates"):
        root = source / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                result[path.relative_to(source).as_posix()] = path.read_bytes()
    return result


@dataclass(frozen=True)
class MigrationAction:
    path: str
    action: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "action": self.action, "reason": self.reason}


def migration_report(project_root: Path) -> dict[str, Any]:
    manifest_error = ""
    try:
        manifest = installation_manifest(project_root)
    except (OSError, TypeError, ValueError) as exc:
        manifest = None
        manifest_error = str(exc)
    installed = (
        str(manifest.get("agentkit_version", "unknown"))
        if manifest
        else "invalid-manifest" if manifest_error else detect_legacy_version(project_root)
    )
    tracked = {
        str(item["path"]): item
        for item in (manifest or {}).get("resources", [])
        if isinstance(item, dict) and "path" in item
    }
    desired = _source_resources()
    actions: list[MigrationAction] = []
    for relative, content in desired.items():
        current = project_root / ".agent" / relative
        wanted_hash = _digest_bytes(content)
        baseline = tracked.get(relative)
        if not current.exists():
            actions.append(MigrationAction(relative, "create", "resource is missing"))
        elif _digest(current) == wanted_hash:
            actions.append(MigrationAction(relative, "unchanged", "resource already matches 1.0"))
        elif relative == "AGENT.md":
            actions.append(MigrationAction(relative, "preserve", "AGENT.md is user-owned"))
        elif baseline and baseline.get("strategy") == "preserved-customization":
            actions.append(
                MigrationAction(relative, "preserve", "resource is marked as a customization")
            )
        elif baseline and _digest(current) == baseline.get("sha256"):
            actions.append(MigrationAction(relative, "update", "managed baseline is unchanged"))
        else:
            actions.append(
                MigrationAction(
                    relative,
                    "preserve",
                    "customized or legacy resource; write an update candidate",
                )
            )
    config = project_root / ".agent" / "agentkit.toml"
    if not config.is_file():
        actions.append(MigrationAction("agentkit.toml", "create", "configuration is missing"))
    action_payload = [item.to_dict() for item in actions]
    return {
        "version": MIGRATION_REPORT_VERSION,
        "installed_version": installed,
        "target_version": PACKAGE_VERSION,
        "compatible": installed not in {"unsupported-pre-0.4", "invalid-manifest"},
        "changes_required": any(
            item["action"] in {"create", "update", "preserve"}
            for item in action_payload
        ),
        "blocking_conflicts": (
            [f"Installation manifest is invalid: {manifest_error}"]
            if manifest_error
            else []
        ),
        "actions": action_payload,
        "generated_at": _now(),
    }


@contextmanager
def _migration_lock(project_root: Path):
    path = project_root / ".agent" / "state" / "migration.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"Another AgentKit migration is active: {path}") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode())
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


def _ensure_current_resources(project_root: Path) -> None:
    from .evals.resources import ensure_evaluation_files
    from .init_project import initialize_project
    from .model_runtime.resources import ensure_model_runtime_files
    from .quality.resources import ensure_quality_project_files
    from .quality.resources_ci import ensure_quality_ci_files
    from .quality.resources_gate import ensure_quality_gate_project_files
    from .quality.resources_hotspot import ensure_hotspot_context_files
    from .quality.resources_routing import ensure_quality_routing_files
    from .release_resources import ensure_release_files

    initialize_project(project_root, install_graphify_skill=False)
    ensure_quality_project_files(project_root)
    ensure_quality_gate_project_files(project_root)
    ensure_hotspot_context_files(project_root)
    ensure_quality_routing_files(project_root)
    ensure_quality_ci_files(project_root)
    ensure_evaluation_files(project_root)
    ensure_model_runtime_files(project_root)
    ensure_release_files(project_root)


def _apply_migration(project_root: Path) -> dict[str, Any]:
    report = migration_report(project_root)
    if not report["compatible"]:
        report["blocking_conflicts"] = [
            "Automatic upgrades require AgentKit 0.4.0 or later"
        ]
        return report
    _ensure_current_resources(project_root)
    source = _source_resources()
    manifest = installation_manifest(project_root)
    tracked = {
        str(item["path"]): item
        for item in (manifest or {}).get("resources", [])
        if isinstance(item, dict) and "path" in item
    }
    migration_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_root = project_root / ".agent" / "backups" / migration_id
    candidate_root = project_root / ".agent" / "update-candidates"
    applied: list[str] = []
    preserved: list[str] = []
    for relative, content in source.items():
        target = project_root / ".agent" / relative
        if relative == "AGENT.md" and target.exists():
            preserved.append(relative)
            continue
        baseline = tracked.get(relative)
        safe = not target.exists() or (
            baseline is not None
            and baseline.get("strategy") != "preserved-customization"
            and _digest(target) == baseline.get("sha256")
        )
        if target.exists() and _digest(target) == _digest_bytes(content):
            continue
        if not safe:
            candidate = candidate_root / relative
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(content)
            preserved.append(relative)
            continue
        if target.exists():
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        applied.append(relative)
    from .release_resources import ensure_release_files

    ensure_release_files(project_root)
    previous = str(
        (manifest or {}).get("agentkit_version", report["installed_version"])
    )
    manifest_path = record_installation_manifest(
        project_root,
        overwrite=True,
        previous_version=previous,
    )
    if preserved:
        manifest_payload = installation_manifest(project_root)
        if manifest_payload is not None:
            preserved_set = set(preserved)
            for resource in manifest_payload.get("resources", []):
                if resource.get("path") in preserved_set:
                    resource["strategy"] = "preserved-customization"
            _atomic_json(manifest_path, manifest_payload)
    report.update(
        applied=applied,
        preserved=preserved,
        backup=str(backup_root) if backup_root.exists() else "",
        installation_manifest=str(manifest_path),
    )
    reports = project_root / ".agent" / "state" / "migrations"
    _atomic_json(reports / f"{migration_id}.json", report)
    return report


def apply_migration(project_root: Path) -> dict[str, Any]:
    with _migration_lock(project_root):
        return _apply_migration(project_root)
