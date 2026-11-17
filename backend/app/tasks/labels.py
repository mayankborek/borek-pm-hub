"""Labels already used in a project, so the label picker can suggest them (search or create).

Labels have no table of their own: they live on the tasks (`tasks.labels`). A new label is
created simply by saving it on a task; this module only reads what is there.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.validation import like_escape
from app.tasks.models import Task
from app.tasks.schemas import LabelOut

MAX_LABEL_SUGGESTIONS = 100


async def list_labels(
    session: AsyncSession, project_id: uuid.UUID, q: str | None, limit: int
) -> list[LabelOut]:
    """Labels on the project's active tasks, most used first. Archived tasks do not count.

    Spellings are kept exactly as stored ("Backend" and "backend" are two labels), because the
    task filter `?label=` matches the exact spelling too.
    """
    used = (
        select(func.unnest(Task.labels).label("name"))
        .where(Task.project_id == project_id, Task.archived_at.is_(None))
        .subquery()
    )
    count = func.count().label("task_count")
    stmt = select(used.c.name, count).group_by(used.c.name)
    if q and q.strip():
        stmt = stmt.where(used.c.name.ilike(f"%{like_escape(q.strip())}%", escape="\\"))
    stmt = stmt.order_by(count.desc(), func.lower(used.c.name), used.c.name).limit(limit)
    rows = await session.execute(stmt)
    return [LabelOut(name=name, task_count=n) for name, n in rows]
