from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from agentkit.models import RunMode

from .models import (
    AcceptanceSpec,
    BudgetExpectation,
    EvaluationManifest,
    QualityExpectation,
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_SECRET_KEY_RE = re.compile(r"(?:secret|token|password|api[_-]?key|authorization|cookie)", re.I)


def _strip_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote:
            escaped = True
            continue
        if char in {'"', "'"}:
            quote = None if quote == char else char if quote is None else quote
        elif char == "#" and quote is None:
            return line[:index]
    return line


def _split_inline(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\" and quote:
            current.append(char)
            escaped = True
            continue
        if char in {'"', "'"}:
            quote = None if quote == char else char if quote is None else quote
            current.append(char)
            continue
        if quote is None:
            if char in "[{(":
                depth += 1
            elif char in "]})":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
                continue
        current.append(char)
    parts.append("".join(current).strip())
    return parts


def _scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {'"', "'"} and value[-1:] == value[0]:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [_scalar(item) for item in _split_inline(inner)]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)", value):
        return float(value)
    return value


def _minimal_yaml_load(text: str) -> Any:
    tokens: list[tuple[int, str]] = []
    for raw in text.splitlines():
        clean = _strip_comment(raw).rstrip()
        if not clean.strip():
            continue
        if "\t" in clean[: len(clean) - len(clean.lstrip())]:
            raise ValueError("YAML indentation must use spaces")
        tokens.append((len(clean) - len(clean.lstrip(" ")), clean.strip()))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(tokens):
            return {}, index
        is_list = tokens[index][1].startswith("- ") or tokens[index][1] == "-"
        container: Any = [] if is_list else {}
        while index < len(tokens):
            current_indent, content = tokens[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"Unexpected YAML indentation near: {content}")
            if is_list:
                if not (content.startswith("- ") or content == "-"):
                    break
                item = content[1:].strip()
                if not item:
                    if index + 1 >= len(tokens) or tokens[index + 1][0] <= indent:
                        container.append(None)
                        index += 1
                    else:
                        value, index = parse_block(index + 1, tokens[index + 1][0])
                        container.append(value)
                    continue
                container.append(_scalar(item))
                index += 1
                continue
            if content.startswith("- "):
                break
            if ":" not in content:
                raise ValueError(f"Expected YAML mapping entry near: {content}")
            key, raw_value = content.split(":", 1)
            key = key.strip()
            if not key:
                raise ValueError("YAML mapping keys cannot be empty")
            raw_value = raw_value.strip()
            if raw_value:
                container[key] = _scalar(raw_value)
                index += 1
                continue
            if index + 1 < len(tokens) and tokens[index + 1][0] > indent:
                value, index = parse_block(index + 1, tokens[index + 1][0])
                container[key] = value
            else:
                container[key] = {}
                index += 1
        return container, index

    if not tokens:
        return {}
    payload, consumed = parse_block(0, tokens[0][0])
    if consumed != len(tokens):
        raise ValueError("Could not parse the complete YAML document")
    return payload


def _load_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except ImportError:
            payload = _minimal_yaml_load(text)
        else:
            payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError(f"Evaluation manifest must be a mapping: {path}")
    return payload


def _relative_path(value: Any, *, name: str) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{name} must be a safe relative path")
    return path.as_posix()


def _string_list(value: Any, *, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be an array of strings")
    return tuple(_relative_path(item, name=name) for item in value)


def _commands(value: Any) -> tuple[tuple[str, ...], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("acceptance.commands must be an array")
    commands: list[tuple[str, ...]] = []
    for item in value:
        if not isinstance(item, list) or not item or not all(isinstance(part, str) for part in item):
            raise ValueError("Each acceptance command must be a non-empty argv array")
        commands.append(tuple(item))
    return tuple(commands)


def _table(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _experiment(value: Any) -> dict[str, str | int | float | bool]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("experiment must be a mapping")
    result: dict[str, str | int | float | bool] = {}
    for key, item in value.items():
        text_key = str(key)
        if _SECRET_KEY_RE.search(text_key):
            raise ValueError(f"Secret-like experiment key is not allowed: {text_key}")
        if not isinstance(item, (str, int, float, bool)):
            raise ValueError(f"experiment.{text_key} must be a scalar")
        result[text_key] = item
    return result


def manifest_from_dict(payload: dict[str, Any]) -> EvaluationManifest:
    task_id = str(payload.get("id", "")).strip().lower()
    if not _ID_RE.fullmatch(task_id):
        raise ValueError("Evaluation id must match [a-z0-9][a-z0-9._-]{2,127}")
    task = str(payload.get("task", "")).strip()
    if not task:
        raise ValueError("Evaluation task cannot be empty")
    mode = str(payload.get("mode", "standard")).lower()
    if mode not in {item.value for item in RunMode} - {RunMode.AUTO.value}:
        raise ValueError("Evaluation mode must be fast, standard, or deep")
    repetitions = int(payload.get("repetitions", 1))
    if repetitions <= 0:
        raise ValueError("Evaluation repetitions must be positive")
    acceptance = _table(payload, "acceptance")
    quality = _table(payload, "quality")
    budget = _table(payload, "budget")
    new_critical = int(quality.get("allow_new_critical_hotspots", 0))
    if new_critical < 0:
        raise ValueError("quality.allow_new_critical_hotspots must be zero or positive")
    max_agent_calls = budget.get("max_agent_calls")
    max_duration = budget.get("max_duration_seconds")
    if max_agent_calls is not None and int(max_agent_calls) <= 0:
        raise ValueError("budget.max_agent_calls must be positive")
    if max_duration is not None and float(max_duration) <= 0:
        raise ValueError("budget.max_duration_seconds must be positive")
    return EvaluationManifest(
        version=int(payload.get("version", 1)),
        id=task_id,
        repository_fixture=_relative_path(
            payload.get("repository_fixture"), name="repository_fixture"
        ),
        mode=mode,
        task=task,
        repetitions=repetitions,
        smoke=bool(payload.get("smoke", False)),
        integration=bool(payload.get("integration", False)),
        human_accepted=(
            bool(payload.get("human_accepted"))
            if payload.get("human_accepted") is not None
            else None
        ),
        acceptance=AcceptanceSpec(
            commands=_commands(acceptance.get("commands")),
            required_files=_string_list(
                acceptance.get("required_files"), name="acceptance.required_files"
            ),
            forbidden_files=_string_list(
                acceptance.get("forbidden_files"), name="acceptance.forbidden_files"
            ),
        ),
        quality=QualityExpectation(allow_new_critical_hotspots=new_critical),
        budget=BudgetExpectation(
            max_agent_calls=int(max_agent_calls) if max_agent_calls is not None else None,
            max_duration_seconds=float(max_duration) if max_duration is not None else None,
        ),
        experiment=_experiment(payload.get("experiment")),
    )


def load_manifest(path: Path) -> EvaluationManifest:
    return manifest_from_dict(_load_payload(path))


def manifest_fingerprint(manifest: EvaluationManifest) -> str:
    canonical = json.dumps(
        manifest.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
