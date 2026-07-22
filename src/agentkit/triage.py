from __future__ import annotations

from .models import RunMode, TriageResult

_DEEP_KEYWORDS = {
    "auth", "authorization", "authentication", "permission", "secret", "credential",
    "migration", "schema", "database", "postgres", "production", "deploy", "rollback",
    "queue", "worker", "thread", "concurrency", "async", "race", "payment", "billing",
    "delete data", "public api", "breaking change", "security", "oauth", "token",
    "авторизац", "аутентификац", "миграц", "баз", "продакш", "депло", "очеред",
    "поток", "конкурент", "секрет", "безопасност", "удалени", "публичн",
}
_FAST_KEYWORDS = {
    "typo", "spelling", "readme", "documentation", "docs", "comment", "formatting",
    "опечат", "документац", "комментар", "форматирован", "текст",
}


def classify_task(task: str, requested: RunMode) -> TriageResult:
    normalized = task.lower()
    reasons: list[str] = []
    if requested is not RunMode.AUTO:
        mode = requested
        reasons.append("execution mode explicitly requested")
    elif any(keyword in normalized for keyword in _DEEP_KEYWORDS):
        mode = RunMode.DEEP
        reasons.append("task contains high-risk domain keywords")
    elif any(keyword in normalized for keyword in _FAST_KEYWORDS):
        mode = RunMode.FAST
        reasons.append("task appears local and documentation-oriented")
    else:
        mode = RunMode.STANDARD
        reasons.append("ordinary code change without confirmed high-risk trigger")

    core = [
        "task-triage",
        "repository-context",
        "requirements-contract",
        "implementation",
        "verification-router",
        "adversarial-review",
        "delivery-summary",
    ]
    if mode is not RunMode.FAST:
        core.insert(3, "change-planner")
        core.insert(-2, "risk-based-testing")
    if mode is RunMode.DEEP:
        core.extend(["architecture-guard", "engineering-balance"])
        if any(item in normalized for item in ("database", "postgres", "migration", "schema", "баз", "миграц")):
            core.append("database-review")
        if any(item in normalized for item in ("thread", "async", "queue", "worker", "race", "поток", "очеред")):
            core.append("concurrency-review")
        if any(item in normalized for item in ("auth", "secret", "token", "security", "авторизац", "секрет")):
            core.append("security-review")
    return TriageResult(mode=mode, risk_reasons=reasons, selected_skills=list(dict.fromkeys(core)))
