"""Daily jobs: tell leads and Managers about milestones that started running late, then delete
notifications older than 90 days.

Run once a day, for example from a scheduled job:  python -m scripts.daily_jobs
Uses DATABASE_URL like the app. Safe to run more than once a day: each milestone is reported
once per due date.
"""

import asyncio

from app.core.database import get_engine, get_sessionmaker
from app.notifications.events import milestones_running_late
from app.notifications.service import delete_old


async def main() -> tuple[int, int]:
    async with get_sessionmaker()() as session:
        late = await milestones_running_late(session)
        await session.commit()
        deleted = await delete_old(session)
    await get_engine().dispose()
    return late, deleted


if __name__ == "__main__":
    late, deleted = asyncio.run(main())
    print(f"Running late reported: {late}. Old notifications deleted: {deleted}.")
