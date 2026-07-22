from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class RunState:
    def __init__(self, project_root: Path) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"{stamp}-{uuid4().hex[:8]}"
        self.directory = project_root / ".agent" / "state" / "runs" / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        latest = project_root / ".agent" / "state" / "latest"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(self.run_id, encoding="utf-8")

    def write_json(self, name: str, payload: object) -> Path:
        path = self.directory / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_text(self, name: str, content: str) -> Path:
        path = self.directory / name
        path.write_text(content, encoding="utf-8")
        return path
