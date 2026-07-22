#!/usr/bin/env python3
"""Print a compact repository tree suitable for an agent's initial context."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

DEFAULT_IGNORED = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}


def iter_tree(root: Path, max_depth: int, ignored: set[str]) -> list[str]:
    lines = [root.name + "/"]

    def visit(directory: Path, prefix: str, depth: int) -> None:
        if depth >= max_depth:
            return
        try:
            entries = sorted(
                (entry for entry in directory.iterdir() if entry.name not in ignored),
                key=lambda item: (not item.is_dir(), item.name.lower()),
            )
        except PermissionError:
            lines.append(prefix + "└── <permission denied>")
            return

        for index, entry in enumerate(entries):
            last = index == len(entries) - 1
            connector = "└── " if last else "├── "
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
            if entry.is_dir() and not entry.is_symlink():
                visit(entry, prefix + ("    " if last else "│   "), depth + 1)

    visit(root, "", 0)
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=".", help="Repository root")
    parser.add_argument("--max-depth", type=int, default=3, help="Maximum directory depth")
    parser.add_argument("--ignore", action="append", default=[], help="Additional ignored name")
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    if args.max_depth < 1:
        parser.error("--max-depth must be at least 1")

    ignored = DEFAULT_IGNORED | set(args.ignore)
    print(os.linesep.join(iter_tree(root, args.max_depth, ignored)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
