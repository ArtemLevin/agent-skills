from __future__ import annotations

import subprocess
from pathlib import Path


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def is_git_repository(project_root: Path) -> bool:
    return _git(project_root, "rev-parse", "--is-inside-work-tree").returncode == 0


def current_head(project_root: Path) -> str:
    result = _git(project_root, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else ""


def changed_files(project_root: Path) -> list[str]:
    result = _git(project_root, "status", "--porcelain=v1", "-uall")
    if result.returncode != 0:
        return []
    files: list[str] = []
    for raw in result.stdout.splitlines():
        if len(raw) < 4:
            continue
        path = raw[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path.strip('"'))
    return sorted(dict.fromkeys(files))


def diff_text(project_root: Path, *, max_chars: int = 30_000) -> str:
    unstaged = _git(project_root, "diff", "--no-ext-diff", "--unified=3").stdout
    staged = _git(project_root, "diff", "--cached", "--no-ext-diff", "--unified=3").stdout
    combined = (staged + "\n" + unstaged).strip()
    if len(combined) > max_chars:
        return combined[:max_chars] + "\n... [diff truncated by AgentKit]"
    return combined
