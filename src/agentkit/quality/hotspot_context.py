from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentkit.config import ContextConfig
from agentkit.context_cache import ContextCache

_CONTEXT_VERSION = "1"
_WORD_RE = re.compile(r"[\w.-]+", re.UNICODE)


@dataclass(frozen=True)
class RankedContextCandidate:
    file: str
    symbol: str
    kind: str
    line_start: int | None
    line_end: int | None
    task_score: float
    quality_score: float
    graph_score: float
    total_score: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


@dataclass(frozen=True)
class HotspotContext:
    version: int
    task: str
    source_snapshot: str
    source_fingerprint: str
    graph_available: bool
    cache_key: str
    fingerprint: str
    cache_hit: bool
    candidates: tuple[RankedContextCandidate, ...]
    warnings: tuple[str, ...]
    content: str

    def to_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        data = asdict(self)
        data["candidates"] = [item.to_dict() for item in self.candidates]
        data["warnings"] = list(self.warnings)
        if not include_content:
            data.pop("content", None)
        data["content_chars"] = len(self.content)
        return data


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _WORD_RE.findall(value) if len(token) >= 3 and not token.isdigit()}


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    return float(value) if isinstance(value, (int, float)) else 0.0


def _identity(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("file") or item.get("dir") or "").replace("\\", "/"),
        str(item.get("class_name") or item.get("class") or ""),
        str(item.get("name") or ""),
    )


def _status_weight(status: str) -> float:
    return {"normal": 0.0, "warning": 0.25, "critical": 0.65, "emergency": 1.0}.get(status.lower(), 0.1)


class HotspotContextCompiler:
    def __init__(self, project_root: Path, config: ContextConfig) -> None:
        self.project_root = project_root
        self.config = config
        cache_path = Path(config.cache_path).expanduser()
        if not cache_path.is_absolute():
            cache_path = project_root / cache_path
        self.cache = ContextCache(cache_path) if config.cache_enabled else None

    def _latest_run(self) -> str:
        for pointer in ("quality-latest", "latest"):
            path = self.project_root / ".agent" / "state" / pointer
            if path.is_file():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    return value
        raise FileNotFoundError("No AgentKit run containing quality evidence exists")

    def _snapshot_path(self, run_id: str) -> Path:
        resolved = self._latest_run() if run_id == "latest" else run_id
        run_dir = self.project_root / ".agent" / "state" / "runs" / resolved
        for name in ("quality-after.json", "quality-before.json"):
            path = run_dir / name
            if path.is_file():
                return path
        raise FileNotFoundError(f"No quality snapshot exists in {run_dir}")

    def _graph_text(self, run_id: str) -> tuple[str, bool]:
        resolved = self._latest_run() if run_id == "latest" else run_id
        for path in (
            self.project_root / ".agent" / "state" / "runs" / resolved / "graph.json",
            self.project_root / "graphify-out" / "graph.json",
        ):
            if path.is_file():
                try:
                    return path.read_text(encoding="utf-8", errors="replace")[:100_000], True
                except OSError:
                    pass
        return "", False

    def _line_range(self, relative: str, symbol: str, class_name: str) -> tuple[int | None, int | None]:
        path = self.project_root / relative
        if path.suffix.lower() not in {".py", ".pyi"} or not path.is_file():
            return None, None
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError, UnicodeError):
            return None, None
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or node.name != symbol:
                continue
            if class_name and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not any(isinstance(parent, ast.ClassDef) and parent.name == class_name and node in ast.walk(parent) for parent in tree.body):
                    continue
            return int(node.lineno), int(getattr(node, "end_lineno", node.lineno))
        return None, None

    def _rank(self, task: str, hotspots: list[dict[str, Any]], graph_text: str, limit: int) -> tuple[RankedContextCandidate, ...]:
        task_tokens = _tokens(task)
        graph_lower = graph_text.lower()
        ranked: list[RankedContextCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for item in hotspots:
            identity = _identity(item)
            if identity in seen:
                continue
            seen.add(identity)
            relative, class_name, symbol = identity
            if not relative:
                continue
            searchable = " ".join((relative, class_name, symbol, " ".join(map(str, item.get("reasons", []))))).lower()
            matched = sorted(token for token in task_tokens if token in searchable)
            task_score = min(1.0, len(matched) / max(1, min(4, len(task_tokens)))) if task_tokens else 0.0
            quality_score = min(1.0, max(
                _number(item.get("rank_score")),
                _number(item.get("status_score")) / 100.0,
                _number(item.get("complexity")) / 50.0,
                _number(item.get("refactoring_pressure")) / 100.0,
                _number(item.get("overengineering_pressure")) / 100.0,
                _status_weight(str(item.get("status", ""))),
            ))
            graph_terms = [term.lower() for term in (relative, class_name, symbol) if term]
            graph_hits = sum(1 for term in graph_terms if term in graph_lower)
            graph_score = min(1.0, graph_hits / max(1, len(graph_terms))) if graph_text else 0.0
            total = round(task_score * 0.60 + graph_score * 0.25 + quality_score * 0.15, 6)
            reasons: list[str] = []
            if matched:
                reasons.append("task tokens: " + ", ".join(matched[:6]))
            if graph_score:
                reasons.append("referenced by Graphify evidence")
            if quality_score:
                reasons.append(f"quality severity {quality_score:.2f}")
            line_start, line_end = self._line_range(relative, symbol, class_name)
            ranked.append(RankedContextCandidate(relative, symbol, str(item.get("kind", "")), line_start, line_end, round(task_score, 6), round(quality_score, 6), round(graph_score, 6), total, tuple(reasons)))
        ranked.sort(key=lambda item: (-item.total_score, item.file, item.symbol))
        relevant = [item for item in ranked if item.task_score > 0 or item.graph_score > 0]
        return tuple((relevant or ranked)[:max(1, limit)])

    def _render(self, task: str, candidates: tuple[RankedContextCandidate, ...], warnings: tuple[str, ...]) -> str:
        lines = ["# AgentKit hotspot-aware context", "", "## Task", "", task.strip(), "", "## Ranked quality context", ""]
        if not candidates:
            lines.append("- No bounded quality candidates were available.")
        for item in candidates:
            location = item.file if item.line_start is None else f"{item.file}:{item.line_start}-{item.line_end}"
            symbol = f" — `{item.symbol}`" if item.symbol else ""
            lines.append(f"- `{location}`{symbol} (score {item.total_score:.3f})")
            lines.extend(f"  - {reason}" for reason in item.reasons)
        lines.extend(["", "## Boundaries", "", "- Quality metrics are navigation evidence, not proof of a defect.", "- Confirm selected symbols in source and tests before editing.", "- Omitted hotspots are not proven irrelevant.", "- Do not broaden implementation merely to improve a global quality score."])
        if warnings:
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {item}" for item in warnings)
        content = "\n".join(lines).rstrip() + "\n"
        if len(content) > self.config.max_context_chars:
            marker = "\n[Hotspot context truncated]\n"
            content = content[:max(0, self.config.max_context_chars - len(marker))] + marker
        return content

    def compile(self, *, task: str, run_id: str = "latest", limit: int | None = None, use_cache: bool = True) -> HotspotContext:
        if not task.strip():
            raise ValueError("Task cannot be empty")
        snapshot_path = self._snapshot_path(run_id)
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Quality snapshot must be a JSON object")
        hotspots = payload.get("hotspots", [])
        if not isinstance(hotspots, list):
            hotspots = []
        graph_text, graph_available = self._graph_text(run_id)
        selected_limit = max(1, limit or self.config.max_candidate_files)
        source_fingerprint = str(payload.get("source_fingerprint", ""))
        key_payload = json.dumps({"task": " ".join(task.split()), "run_id": run_id, "limit": selected_limit}, ensure_ascii=False, sort_keys=True)
        cache_key = hashlib.sha256(key_payload.encode("utf-8")).hexdigest()
        digest = hashlib.sha256()
        digest.update(_CONTEXT_VERSION.encode("ascii"))
        digest.update(key_payload.encode("utf-8"))
        digest.update(hashlib.sha256(snapshot_path.read_bytes()).digest())
        digest.update(hashlib.sha256(graph_text.encode("utf-8")).digest())
        for item in hotspots:
            if isinstance(item, dict):
                relative, _, _ = _identity(item)
                path = self.project_root / relative
                if path.is_file():
                    digest.update(relative.encode("utf-8"))
                    digest.update(hashlib.sha256(path.read_bytes()).digest())
        fingerprint = digest.hexdigest()
        if self.cache is not None and use_cache:
            entry = self.cache.get("hotspot_context", cache_key, fingerprint=fingerprint)
            if entry is not None:
                cached = entry.payload
                return HotspotContext(1, str(cached.get("task", task)), str(cached.get("source_snapshot", snapshot_path)), str(cached.get("source_fingerprint", source_fingerprint)), bool(cached.get("graph_available", False)), cache_key, fingerprint, True, tuple(RankedContextCandidate(**{**item, "reasons": tuple(item.get("reasons", []))}) for item in cached.get("candidates", []) if isinstance(item, dict)), tuple(cached.get("warnings", [])), str(cached.get("content", "")))
        warnings: list[str] = []
        availability = str(payload.get("availability", ""))
        if availability not in {"available", "partial"}:
            warnings.append(f"Quality evidence availability is {availability or 'unknown'}")
        if bool(payload.get("truncated", False)):
            warnings.append("Quality snapshot was truncated")
        if not graph_available:
            warnings.append("Graphify evidence was unavailable; graph score is zero")
        candidates = self._rank(task, [item for item in hotspots if isinstance(item, dict)], graph_text, selected_limit)
        content = self._render(task, candidates, tuple(warnings))
        result = HotspotContext(1, task.strip(), snapshot_path.relative_to(self.project_root).as_posix(), source_fingerprint, graph_available, cache_key, fingerprint, False, candidates, tuple(warnings), content)
        if self.cache is not None and use_cache:
            self.cache.put("hotspot_context", cache_key, fingerprint=fingerprint, payload=result.to_dict(), metadata={"source_snapshot": result.source_snapshot, "candidate_count": len(candidates)}, ttl_seconds=self.config.cache_ttl_seconds)
        return result
