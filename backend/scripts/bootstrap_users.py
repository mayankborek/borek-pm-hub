"""Make sure one PM and one developer account exist, with passwords, for AUTH_MODE=local.

Safe to run on every start: it only creates what is missing and never changes other data.
Passwords come from the environment (never from the code); a missing or short password skips
that account.

  BOOTSTRAP_PM_EMAIL / BOOTSTRAP_PM_PASSWORD     (default email qa.pm@borek.test)
  BOOTSTRAP_DEV_EMAIL / BOOTSTRAP_DEV_PASSWORD   (default email qa.dev@borek.test)
  --reset-passwords   also set the password of accounts that already exist

Run from the backend folder:  python -m scripts.bootstrap_users
"""

import argparse
import asyncio
import os
import uuid
from collections.abc import Mapping

from dotenv import dotenv_values
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.common.enums import GlobalRole
from app.core.database import get_engine, get_sessionmaker
from app.users.models import User

MIN_PASSWORD_LENGTH = 12

# (id, display name, role, email variable, default email, password variable)
ACCOUNTS = [
    (
        uuid.UUID("00000000-0000-4000-8000-000000000021"),
        "QA PM",
        GlobalRole.PM,
        "BOOTSTRAP_PM_EMAIL",
        "qa.pm@borek.test",
        "BOOTSTRAP_PM_PASSWORD",
    ),
    (
        uuid.UUID("00000000-0000-4000-8000-000000000022"),
        "QA Developer",
        GlobalRole.DEVELOPER,
        "BOOTSTRAP_DEV_EMAIL",
        "qa.dev@borek.test",
        "BOOTSTRAP_DEV_PASSWORD",
    ),
]


async def ensure_accounts(
    session: AsyncSession, env: Mapping[str, str], reset_passwords: bool = False
) -> list[str]:
    """Create the missing accounts; returns one line per account saying what happened."""
    report: list[str] = []
    for user_id, name, role, email_var, default_email, password_var in ACCOUNTS:
        email = env.get(email_var, default_email).strip().lower()
        password = env.get(password_var, "")
        if len(password) < MIN_PASSWORD_LENGTH:
            report.append(f"skipped {email}: set {password_var} ({MIN_PASSWORD_LENGTH}+ chars)")
            continue
        user = await session.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            session.add(
                User(
                    id=user_id,
                    name=name,
                    email=email,
                    global_role=role.value,
                    password_hash=hash_password(password),
                )
            )
            report.append(f"created {email} ({role.value})")
        elif reset_passwords or user.password_hash is None:
            user.password_hash = hash_password(password)
            user.failed_login_count = 0
            user.locked_until = None
            report.append(f"password set for {email}")
        else:
            report.append(f"kept {email}")
    await session.flush()
    return report


def read_environment() -> dict[str, str]:
    """backend/.env (when present, e.g. running outside Docker) overridden by real variables."""
    values = {k: v for k, v in dotenv_values(".env").items() if v is not None}
    return {**values, **os.environ}


async def main(reset_passwords: bool) -> None:
    async with get_sessionmaker()() as session, session.begin():
        for line in await ensure_accounts(session, read_environment(), reset_passwords):
            print(line)
    await get_engine().dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the QA PM and developer accounts.")
    parser.add_argument("--reset-passwords", action="store_true")
    asyncio.run(main(parser.parse_args().reset_passwords))
