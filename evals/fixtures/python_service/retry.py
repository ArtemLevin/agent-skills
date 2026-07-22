from __future__ import annotations


def schedule_retry(queue: list[str], job_id: str) -> list[str]:
    """Schedule a retry while preserving insertion order."""
    queue.append(job_id)
    return queue
