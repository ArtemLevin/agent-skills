from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .config import ContextConfig
from .context_cache import ContextCache
from .project_profile import ProjectProfile, list_project_files, load_or_create_profile


COMPILER_VERSION = "1"
PHASES = ("plan", "implementation", "review", "targeted_fix")

_PHASE_RULES = {
    "plan": (
        "Produce a bounded change plan. Do not edit files. Map acceptance criteria to files, "
        "symbols, checks, rollback concerns, and unresolved assumptions."
    ),
    "implementation": (
        "Implement the smallest complete behavioral change. Confirm candidate files in source before "
        "editing, preserve unrelated work, and keep tests focused on the regression risk."
    ),
    "review": (
        "Review read-only. Try to disprove correctness against the task contract, executed checks, and "
        "diff. Report only evidenced P0-P3 findings; do not modify files."
    ),
    "targeted_fix": (
        "Fix only the supplied blocking finding or failed check. Do not broaden scope, redesign adjacent "
        "code, or repeat already successful work."
    ),
}

_WORD_RE = re.compile(r"[\w.-]+", re.UNICODE)


@dataclass(frozen=True)
class CompiledContext:
    version: int
    phase: str
    cache_key: str
    fingerprint: str
    cache_hit: bool
    profile_fingerprint: str
    selected_skills: list[str]
    candidate_files: list[str]
    symbol_inventory: dict[str, list[str]]
    content: str

    def to_dict(self, *, include_content: bool = True) -> dict[str, object]:
        payload = asdict(self)
        if not include_content:
            payload.pop("content", None)
        payload["content_chars"] = len(self.content)
        return payload


class ContextCompiler:
    def __init__(self, project_root: Path, config: ContextConfig) -> None:
        # Windows runners may expose the same temporary directory through both
        # an 8.3 short name and its canonical long name. Normalize once before
        # comparing candidate paths so pathlib does not treat them as unrelated.
        self.project_root = project_root.resolve()
        self.config = config
        cache_path = self._resolve(config.cache_path)
        self.cache = ContextCache(cache_path) if config.cache_enabled else None

    def _resolve(self, raw: str) -> Path:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else self.project_root / path

    def _task_tokens(self, task: str) -> set[str]:
        return {
            token.lower()
            for token in _WORD_RE.findall(task)
            if len(token) >= 3 and not token.isdigit()
        }

    def _candidate_files(self, task: str) -> list[Path]:
        files, _ = list_project_files(
            self.project_root,
            max_files=self.config.max_profile_files,
        )
        tokens = self._task_tokens(task)
        supported = {
            ".py",
            ".pyi",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".java",
            ".kt",
            ".go",
            ".rs",
            ".rb",
            ".php",
            ".cs",
            ".cpp",
            ".c",
            ".h",
            ".hpp",
            ".sql",
            ".toml",
            ".yaml",
            ".yml",
            ".json",
            ".md",
        }
        scored: list[tuple[int, str, Path]] = []
        for path in files:
            relative = path.relative_to(self.project_root).as_posix()
            if path.suffix.lower() not in supported and path.name not in {
                "Makefile",
                "Dockerfile",
            }:
                continue
            lowered = relative.lower()
            score = sum(
                4 if token in path.stem.lower() else 1
                for token in tokens
                if token in lowered
            )
            if path.name in {"pyproject.toml", "package.json", "Makefile", "README.md"}:
                score += 1
            scored.append((score, relative, path))
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = [
            path
            for score, _, path in scored
            if score > 0
        ][: self.config.max_candidate_files]
        if not selected:
            selected = [
                path
                for _, _, path in scored[: self.config.max_candidate_files]
            ]
        return selected

    def _symbols_for(self, path: Path) -> list[str]:
        if path.suffix.lower() not in {".py", ".pyi"}:
            return []
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError, UnicodeError):
            return []
        symbols: list[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                symbols.append(f"{prefix} {node.name}(...)")
            elif isinstance(node, ast.ClassDef):
                symbols.append(f"class {node.name}")
            if len(symbols) >= self.config.max_symbols_per_file:
                break
        return symbols

    def _skill_summary(self, name: str) -> str:
        path = self.project_root / ".agent" / "skills" / name / "SKILL.md"
        if not path.is_file():
            return f"{name}: instructions unavailable"
        text = path.read_text(encoding="utf-8", errors="replace")
        description = ""
        match = re.search(
            r"description:\s*>\s*\n(?P<body>(?:\s{2,}.+\n?)+)",
            text,
        )
        if match:
            description = " ".join(
                line.strip() for line in match.group("body").splitlines()
            )
        if not description:
            lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.startswith("#")
            ]
            description = " ".join(lines[:3])
        return f"{name}: {description[:500]}"

    def _fingerprint(
        self,
        *,
        task: str,
        phase: str,
        mode: str,
        profile: ProjectProfile,
        candidates: Iterable[Path],
        selected_skills: list[str],
    ) -> tuple[str, str]:
        key_payload = json.dumps(
            {
                "task": " ".join(task.split()),
                "phase": phase,
                "mode": mode,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        cache_key = hashlib.sha256(key_payload.encode("utf-8")).hexdigest()
        digest = hashlib.sha256()
        digest.update(COMPILER_VERSION.encode("ascii"))
        digest.update(profile.fingerprint.encode("ascii"))
        digest.update(key_payload.encode("utf-8"))
        for path in candidates:
            digest.update(
                path.relative_to(self.project_root).as_posix().encode("utf-8")
            )
            try:
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            except OSError:
                digest.update(b"missing")
        for name in selected_skills:
            path = self.project_root / ".agent" / "skills" / name / "SKILL.md"
            digest.update(name.encode("utf-8"))
            if path.is_file():
                try:
                    digest.update(hashlib.sha256(path.read_bytes()).digest())
                except OSError:
                    digest.update(b"missing")
        return cache_key, digest.hexdigest()

    def _render(
        self,
        *,
        task: str,
        phase: str,
        mode: str,
        profile: ProjectProfile,
        candidates: list[Path],
        selected_skills: list[str],
        symbols: dict[str, list[str]],
    ) -> str:
        lines = [
            "# AgentKit compiled context",
            "",
            f"- Phase: `{phase}`",
            f"- Mode: `{mode}`",
            f"- Profile fingerprint: `{profile.fingerprint}`",
            "",
            "## Task",
            "",
            task.strip(),
            "",
            "## Project profile",
            "",
            f"- Languages: {', '.join(profile.languages) or 'unknown'}",
            f"- Package managers: {', '.join(profile.package_managers) or 'unknown'}",
            f"- Source roots: {', '.join(profile.source_roots) or 'not detected'}",
            f"- Test roots: {', '.join(profile.test_roots) or 'not detected'}",
            f"- Frameworks: {', '.join(profile.frameworks) or 'not detected'}",
            "- Verification commands:",
        ]
        lines.extend(
            f"  - `{' '.join(command)}`"
            for command in profile.verification_commands
        )
        if not profile.verification_commands:
            lines.append("  - none detected")
        lines.extend(["", "## Phase contract", "", _PHASE_RULES[phase], ""])
        lines.extend(["## Selected skills", ""])
        if selected_skills:
            lines.extend(
                f"- {self._skill_summary(name)}"
                for name in selected_skills
            )
        else:
            lines.append(
                "- No explicit skills selected; apply the global AgentKit contract."
            )
        lines.extend(["", "## Candidate files", ""])
        for path in candidates:
            relative = path.relative_to(self.project_root).as_posix()
            lines.append(f"- `{relative}`")
            for symbol in symbols.get(relative, []):
                lines.append(f"  - {symbol}")
        if not candidates:
            lines.append(
                "- No candidate files identified. Use repository search before opening broad context."
            )
        lines.extend(
            [
                "",
                "## Context boundaries",
                "",
                "- This packet is navigation context, not proof of runtime behavior.",
                "- Confirm important relationships in source and tests before editing.",
                "- Read full files only when signatures, symbols, and direct dependencies are insufficient.",
                "- Do not treat omitted files as proven irrelevant.",
            ]
        )
        content = "\n".join(lines).rstrip() + "\n"
        if len(content) > self.config.max_context_chars:
            marker = "\n\n[Context truncated by configured max_context_chars]\n"
            content = (
                content[: max(0, self.config.max_context_chars - len(marker))]
                + marker
            )
        return content

    def compile(
        self,
        *,
        task: str,
        phase: str = "implementation",
        mode: str = "auto",
        selected_skills: list[str] | None = None,
        refresh_profile: bool = False,
        use_cache: bool = True,
    ) -> CompiledContext:
        if not self.config.enabled:
            raise RuntimeError("Context compiler is disabled in configuration")
        if phase not in PHASES:
            raise ValueError(f"Unsupported context phase: {phase}")
        if not task.strip():
            raise ValueError("Context task cannot be empty")
        profile_path = self._resolve(self.config.profile_path)
        profile, _ = load_or_create_profile(
            self.project_root,
            profile_path,
            refresh=refresh_profile,
            max_files=self.config.max_profile_files,
        )
        skills = list(dict.fromkeys(selected_skills or []))
        candidates = self._candidate_files(task)
        relative_candidates = [
            path.relative_to(self.project_root).as_posix()
            for path in candidates
        ]
        symbols = {
            relative: self._symbols_for(path)
            for relative, path in zip(relative_candidates, candidates)
        }
        symbols = {
            key: value
            for key, value in symbols.items()
            if value
        }
        cache_key, fingerprint = self._fingerprint(
            task=task,
            phase=phase,
            mode=mode,
            profile=profile,
            candidates=candidates,
            selected_skills=skills,
        )
        if self.cache is not None and use_cache:
            entry = self.cache.get(
                "compiled_context",
                cache_key,
                fingerprint=fingerprint,
            )
            if entry is not None:
                payload = entry.payload
                return CompiledContext(
                    version=int(payload["version"]),
                    phase=str(payload["phase"]),
                    cache_key=str(payload["cache_key"]),
                    fingerprint=str(payload["fingerprint"]),
                    cache_hit=True,
                    profile_fingerprint=str(payload["profile_fingerprint"]),
                    selected_skills=[
                        str(item)
                        for item in payload.get("selected_skills", [])
                    ],
                    candidate_files=[
                        str(item)
                        for item in payload.get("candidate_files", [])
                    ],
                    symbol_inventory={
                        str(key): [str(item) for item in value]
                        for key, value in dict(
                            payload.get("symbol_inventory", {})
                        ).items()
                    },
                    content=str(payload["content"]),
                )
        content = self._render(
            task=task,
            phase=phase,
            mode=mode,
            profile=profile,
            candidates=candidates,
            selected_skills=skills,
            symbols=symbols,
        )
        compiled = CompiledContext(
            version=1,
            phase=phase,
            cache_key=cache_key,
            fingerprint=fingerprint,
            cache_hit=False,
            profile_fingerprint=profile.fingerprint,
            selected_skills=skills,
            candidate_files=relative_candidates,
            symbol_inventory=symbols,
            content=content,
        )
        if self.cache is not None and use_cache:
            self.cache.put(
                "compiled_context",
                cache_key,
                fingerprint=fingerprint,
                payload=compiled.to_dict(include_content=True),
                metadata={
                    "phase": phase,
                    "profile_fingerprint": profile.fingerprint,
                },
                ttl_seconds=self.config.cache_ttl_seconds,
            )
        return compiled

    def write(
        self,
        compiled: CompiledContext,
        output: Path | None = None,
    ) -> Path:
        if output is None:
            output = (
                self.project_root
                / ".agent"
                / "state"
                / "contexts"
                / f"{compiled.phase}-{compiled.cache_key[:16]}.md"
            )
        elif not output.is_absolute():
            output = self.project_root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(compiled.content, encoding="utf-8")
        return output
