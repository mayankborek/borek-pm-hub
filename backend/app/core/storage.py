"""Where uploaded files live: a folder on disk (UPLOAD_DIR), one file per upload.

Files are named by a random key, never by the user's file name, so a name can not escape the
folder. Files are never deleted when an attachment is archived. To move to Azure Blob Storage
later, only this module changes.
"""

import uuid
from pathlib import Path

import anyio

from app.core.config import get_settings


def _root() -> Path:
    return Path(get_settings().upload_dir)


def path_for(key: str) -> Path:
    return _root() / key


async def save(data: bytes) -> str:
    """Write the bytes to a new file and return its key."""
    key = uuid.uuid4().hex
    root = _root()
    await anyio.to_thread.run_sync(lambda: root.mkdir(parents=True, exist_ok=True))
    await anyio.to_thread.run_sync(path_for(key).write_bytes, data)
    return key
