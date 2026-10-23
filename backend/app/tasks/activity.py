"""Task history (F08): one row per change, written in the same transaction as the change."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.models import Task, TaskActivity

MAX_TEXT = 500  # long descriptions are cut in the history, the task keeps the full text


def _readable(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and len(value) > MAX_TEXT:
        return value[:MAX_TEXT] + "..."
    return value


def snapshot(task: Task, status_name: str, assignee_name: str | None) -> dict[str, Any]:
    """The tracked fields with readable values (names instead of ids)."""
    return {
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "labels": list(task.labels),
        "start_date": task.start_date,
        "due_date": task.due_date,
        "estimate": task.estimate,
        "progress": task.progress,
        "status": status_name,
        "assignee": assignee_name,
        "blocked_reason": task.blocked_reason,
    }


def diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[Any]]:
    return {k: [_readable(old[k]), _readable(new[k])] for k in new if old[k] != new[k]}


def record(
    session: AsyncSession,
    task_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    changes: dict[str, list[Any]] | None = None,
) -> None:
    """Add a history row. The caller commits."""
    session.add(
        TaskActivity(task_id=task_id, actor_id=actor_id, action=action, changes=changes or {})
    )
