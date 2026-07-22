from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import RUN_STATE_VERSION


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class RunState:
    def __init__(
        self,
        project_root: Path,
        *,
        run_id: str | None = None,
        resume: bool = False,
    ) -> None:
        self.project_root = project_root
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = run_id or f"{stamp}-{uuid4().hex[:8]}"
        self.directory = project_root / ".agent" / "state" / "runs" / self.run_id
        if resume:
            if not self.directory.is_dir():
                raise FileNotFoundError(f"Unknown AgentKit run: {self.run_id}")
            payload = self.metadata()
            if payload.get("mutation_started") and not payload.get("mutation_completed"):
                raise RuntimeError(
                    "Run crossed the mutation boundary and requires manual recovery; "
                    "AgentKit will not repeat the mutating command"
                )
            if payload.get("mutation_completed"):
                raise RuntimeError(
                    "Completed mutation cannot be replayed automatically; inspect the "
                    "working tree and start a new verification run"
                )
            self.update(status="running", resumed_at=_now())
        else:
            self.directory.mkdir(parents=True, exist_ok=False)
            self.write_json(
                "run.json",
                {
                    "version": RUN_STATE_VERSION,
                    "run_id": self.run_id,
                    "status": "running",
                    "phase": "preflight",
                    "started_at": _now(),
                    "updated_at": _now(),
                    "mutation_started": False,
                    "mutation_completed": False,
                    "mutation_fingerprint": "",
                    "temporary_worktrees": [],
                    "message": "",
                },
            )
        _atomic_write(project_root / ".agent" / "state" / "latest", self.run_id + "\n")

    @classmethod
    def finish_existing(
        cls,
        project_root: Path,
        run_id: str,
        *,
        status: str,
        phase: str,
        message: str,
    ) -> None:
        directory = project_root / ".agent" / "state" / "runs" / run_id
        path = directory / "run.json"
        if not path.is_file():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(
            status=status,
            phase=phase,
            message=message,
            updated_at=_now(),
            finished_at=_now(),
        )
        _atomic_write(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    @staticmethod
    def incomplete_runs(project_root: Path) -> list[dict[str, Any]]:
        root = project_root / ".agent" / "state" / "runs"
        result: list[dict[str, Any]] = []
        if not root.is_dir():
            return result
        for path in sorted(root.glob("*/run.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                result.append({"run_id": path.parent.name, "status": "corrupt"})
                continue
            if payload.get("status") == "running":
                if payload.get("mutation_started") and not payload.get(
                    "mutation_completed"
                ):
                    payload["status"] = "manual_recovery_required"
                result.append(payload)
        return result

    def metadata(self) -> dict[str, Any]:
        path = self.directory / "run.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def update(self, **changes: object) -> Path:
        payload = self.metadata()
        payload.update(changes)
        payload["updated_at"] = _now()
        return self.write_json("run.json", payload)

    def checkpoint(self, phase: str, payload: object | None = None) -> Path:
        self.update(phase=phase)
        return self.write_json(
            f"checkpoints/{phase}.json",
            {"version": 1, "phase": phase, "created_at": _now(), "payload": payload or {}},
        )

    def mark_mutation_started(self, phase: str) -> None:
        self.update(phase=phase, mutation_started=True, mutation_completed=False)

    def mark_mutation_completed(self, diff: str) -> None:
        fingerprint = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        self.update(mutation_completed=True, mutation_fingerprint=fingerprint)

    def write_json(self, name: str, payload: object) -> Path:
        path = self.directory / name
        _atomic_write(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        return path

    def write_text(self, name: str, content: str) -> Path:
        path = self.directory / name
        _atomic_write(path, content)
        return path
