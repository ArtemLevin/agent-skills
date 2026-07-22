from __future__ import annotations

import importlib.util
import json
import platform
import shutil
import sys
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .context_cache import ContextCache
from .contracts import ARTIFACT_SCHEMAS, DIAGNOSTICS_VERSION, PACKAGE_VERSION, PublicContracts
from .executables import resolve_graphify_executable
from .git import is_git_repository
from .graphify import find_graphify_project_skill
from .installation import installation_manifest, migration_report
from .redaction import redact, redact_text
from .state import RunState


def version_payload(project_root: Path) -> dict[str, Any]:
    try:
        manifest = installation_manifest(project_root)
        manifest_error = ""
    except (OSError, TypeError, ValueError) as exc:
        manifest = None
        manifest_error = str(exc)
    graphify = resolve_graphify_executable()
    return {
        "agentkit_version": PACKAGE_VERSION,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "executable": sys.executable,
        "project_root": str(project_root),
        "installed_project_version": (
            str(manifest.get("agentkit_version"))
            if manifest
            else "invalid" if manifest_error else "unmanaged"
        ),
        "installation_manifest_error": manifest_error,
        "contracts": PublicContracts().to_dict(),
        "optional_dependencies": {
            "openai": importlib.util.find_spec("openai") is not None,
            "yaml": importlib.util.find_spec("yaml") is not None,
            "strictacode": shutil.which("strictacode") is not None,
            "graphify": graphify.found,
        },
        "dependency_executables": {
            "graphify": graphify.to_dict(),
        },
    }


def _check(name: str, passed: bool, message: str, *, required: bool = True) -> dict[str, Any]:
    return {"name": name, "passed": passed, "required": required, "message": message}


def self_test(project_root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    checks.append(_check("python", sys.version_info >= (3, 11), platform.python_version()))
    checks.append(_check("git", is_git_repository(project_root), "Git repository detected"))

    config_path = project_root / ".agent" / "agentkit.toml"
    config_data: dict[str, Any] = {}
    try:
        config_data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        checks.append(_check("configuration", True, str(config_path)))
    except (OSError, ValueError) as exc:
        checks.append(_check("configuration", False, str(exc)))

    try:
        manifest = installation_manifest(project_root)
        manifest_message = (
            "managed installation" if manifest else "run agentkit migrate apply"
        )
    except (OSError, TypeError, ValueError) as exc:
        manifest = None
        manifest_message = f"invalid installation manifest: {exc}"
    checks.append(
        _check(
            "installation_manifest",
            manifest is not None,
            manifest_message,
        )
    )

    schema_root = project_root / ".agent" / "schemas"
    missing_schemas = [name for name in ARTIFACT_SCHEMAS if not (schema_root / name).is_file()]
    checks.append(
        _check(
            "artifact_schemas",
            not missing_schemas,
            "complete" if not missing_schemas else "missing: " + ", ".join(missing_schemas),
        )
    )

    migration = migration_report(project_root)
    checks.append(
        _check(
            "migration",
            not migration["blocking_conflicts"],
            f"target={migration['target_version']}; changes={migration['changes_required']}",
        )
    )

    context = config_data.get("context", {}) if isinstance(config_data, dict) else {}
    cache_raw = str(context.get("cache_path", ".agent/cache/context.db"))
    cache_path = Path(cache_raw)
    if not cache_path.is_absolute():
        cache_path = project_root / cache_path
    try:
        cache = ContextCache(cache_path)
        checks.append(_check("context_cache", True, cache.stats()["path"]))
        if cache.recovery_warning:
            warnings.append(cache.recovery_warning)
    except (OSError, ValueError) as exc:
        checks.append(_check("context_cache", False, str(exc)))

    incomplete = RunState.incomplete_runs(project_root)
    checks.append(
        _check(
            "incomplete_runs",
            not incomplete,
            "none" if not incomplete else f"{len(incomplete)} run(s) require inspection",
        )
    )

    worktree_root = project_root / ".agent" / "worktrees"
    stale_worktrees = (
        [path for path in worktree_root.iterdir() if path.is_dir()]
        if worktree_root.is_dir()
        else []
    )
    checks.append(
        _check(
            "temporary_worktrees",
            not stale_worktrees,
            (
                "none"
                if not stale_worktrees
                else "inspect: " + ", ".join(str(p) for p in stale_worktrees)
            ),
        )
    )

    models = config_data.get("models", {}) if isinstance(config_data, dict) else {}
    models_enabled = bool(models.get("enabled", False)) if isinstance(models, dict) else False
    openai_available = importlib.util.find_spec("openai") is not None
    checks.append(
        _check(
            "openai",
            openai_available or not models_enabled,
            "available" if openai_available else "optional dependency is unavailable",
            required=models_enabled,
        )
    )

    graphify = resolve_graphify_executable()
    graphify_skill = find_graphify_project_skill(project_root)
    graphify_ready = graphify.found and graphify_skill is not None
    checks.append(
        _check(
            "graphify",
            graphify_ready,
            (
                f"{graphify.source}; project skill={graphify_skill}"
                if graphify_ready
                else "run agentkit graph install --platform agents"
            ),
            required=False,
        )
    )
    if not graphify_ready:
        warnings.append("Graphify is not fully connected; run agentkit graph install --platform agents")

    try:
        from .init_project import initialize_project

        with tempfile.TemporaryDirectory(prefix="agentkit path with spaces ") as directory:
            initialize_project(Path(directory), install_graphify_skill=False)
        checks.append(_check("paths_with_spaces", True, "temporary initialization passed"))
    except (OSError, RuntimeError, ValueError) as exc:
        checks.append(_check("paths_with_spaces", False, str(exc)))

    ready = all(item["passed"] for item in checks if item["required"])
    return {"version": 1, "ready": ready, "checks": checks, "warnings": warnings}


def create_diagnostics_bundle(project_root: Path) -> dict[str, Any]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = project_root / ".agent" / "diagnostics" / f"agentkit-diagnostics-{stamp}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {
        "version.json": json.dumps(redact(version_payload(project_root)), indent=2, sort_keys=True),
        "self-test.json": json.dumps(redact(self_test(project_root)), indent=2, sort_keys=True),
        "migration-report.json": json.dumps(
            redact(migration_report(project_root)), indent=2, sort_keys=True
        ),
    }
    config = project_root / ".agent" / "agentkit.toml"
    if config.is_file() and not config.is_symlink():
        raw_config = config.read_text(encoding="utf-8")[:1_000_000]
        try:
            files["agentkit-config.json"] = json.dumps(
                redact(tomllib.loads(raw_config)), indent=2, sort_keys=True
            )
        except tomllib.TOMLDecodeError:
            files["agentkit.toml.redacted"] = redact_text(raw_config)
    manifest = project_root / ".agent" / "installation.json"
    if manifest.is_file() and not manifest.is_symlink():
        raw_manifest = manifest.read_text(encoding="utf-8")[:1_000_000]
        try:
            parsed_manifest = json.loads(raw_manifest)
        except ValueError:
            files["installation.invalid.redacted.txt"] = redact_text(raw_manifest)
        else:
            files["installation.json"] = json.dumps(
                redact(parsed_manifest), indent=2, sort_keys=True
            )
    latest = project_root / ".agent" / "state" / "latest"
    if latest.is_file() and not latest.is_symlink():
        run_id = latest.read_text(encoding="utf-8").strip()
        run_state = project_root / ".agent" / "state" / "runs" / run_id / "run.json"
        if run_state.is_file() and not run_state.is_symlink():
            files["latest-run.json"] = json.dumps(
                redact(json.loads(run_state.read_text(encoding="utf-8"))), indent=2, sort_keys=True
            )
    manifest_payload = {
        "version": DIAGNOSTICS_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "agentkit_version": PACKAGE_VERSION,
        "files": sorted([*files, "manifest.json"]),
        "redacted": True,
    }
    files["manifest.json"] = json.dumps(manifest_payload, indent=2, sort_keys=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content + "\n")
    return {"path": str(output), "manifest": manifest_payload}
