#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{24,}\b"),
)


def main() -> int:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.split(b"\0")
    findings: list[str] = []
    for raw in tracked:
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="replace")
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in PATTERNS):
                findings.append(f"{relative}:{number}: possible secret material")
    if findings:
        print("\n".join(findings))
        return 1
    print(f"secret scan passed for {len(tracked) - 1} tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
