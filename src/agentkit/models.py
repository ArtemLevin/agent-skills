from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class RunMode(StrEnum):
    AUTO = "auto"
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


class Stage(StrEnum):
    PREFLIGHT = "preflight"
    TRIAGE = "triage"
    GRAPH_CONTEXT = "graph_context"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    REVIEW = "review"
    FIX = "fix"
    COMPLETE = "complete"
    FAILED = "failed"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True)
class TriageResult:
    mode: RunMode
    risk_reasons: list[str]
    selected_skills: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"passed": self.passed}


@dataclass(frozen=True)
class ReviewFinding:
    severity: str
    issue: str
    evidence: str = ""
    smallest_fix: str = ""
    file: str = ""

    @property
    def blocking(self) -> bool:
        return self.severity.upper() in {"P0", "P1"}


@dataclass(frozen=True)
class ReviewReport:
    verdict: str
    findings: list[ReviewFinding] = field(default_factory=list)
    raw_output: str = ""

    @property
    def blocking_findings(self) -> list[ReviewFinding]:
        return [finding for finding in self.findings if finding.blocking]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "findings": [asdict(item) for item in self.findings],
            "blocking_count": len(self.blocking_findings),
            "raw_output": self.raw_output,
        }


@dataclass(frozen=True)
class CompletionReport:
    status: str
    mode: RunMode
    changed_files: list[str]
    checks_passed: bool
    review_passed: bool
    blocking_findings: int
    scope_passed: bool
    residual_risks: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return (
            self.status == "ready_for_review"
            and self.checks_passed
            and self.review_passed
            and self.blocking_findings == 0
            and self.scope_passed
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        data["ready"] = self.ready
        return data
