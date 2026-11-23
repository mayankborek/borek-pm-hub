"""Delete notifications older than 90 days (Mayank 23.11.2026: notifications are not business
records, so they are the one thing that is physically deleted).

Run once a day, for example from a scheduled job:  python -m scripts.cleanup_notifications
Uses DATABASE_URL like the app. `--days` changes the age (at least 1).
"""

import argparse
import asyncio

from app.core.database import get_engine, get_sessionmaker
from app.notifications.service import RETENTION_DAYS, delete_old


async def main(days: int) -> int:
    async with get_sessionmaker()() as session:
        deleted = await delete_old(session, days=days)
    await get_engine().dispose()
    return deleted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=RETENTION_DAYS)
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be at least 1")
    print(f"Deleted {asyncio.run(main(args.days))} notifications older than {args.days} days.")
