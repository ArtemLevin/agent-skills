#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from normalize_sdist import normalize_sdist

ROOT = Path(__file__).resolve().parents[1]


def _hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def main() -> int:
    timestamp = subprocess.run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = timestamp
    with (
        tempfile.TemporaryDirectory(prefix="agentkit-build-a-") as first_raw,
        tempfile.TemporaryDirectory(prefix="agentkit-build-b-") as second_raw,
    ):
        first = Path(first_raw)
        second = Path(second_raw)
        for output in (first, second):
            subprocess.run(
                [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output)],
                cwd=ROOT,
                env=environment,
                check=True,
            )
            for sdist in output.glob("*.tar.gz"):
                normalize_sdist(sdist, epoch=int(timestamp))
        left = _hashes(first)
        right = _hashes(second)
    if left != right:
        print(f"non-reproducible build\nfirst={left}\nsecond={right}", file=sys.stderr)
        return 1
    print(f"reproducible artifacts: {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
