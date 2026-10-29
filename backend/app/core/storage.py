"""Where uploaded files live: a folder on disk (UPLOAD_DIR), one file per upload.

Files are named by a random key, never by the user's file name, so a name can not escape the
folder. Files are never deleted when an attachment is archived. To move to Azure Blob Storage
later, only this module changes.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from anyio import AsyncFile

from app.core.config import get_settings


def _root() -> Path:
    return Path(get_settings().upload_dir)


def path_for(key: str) -> Path:
    return _root() / key


@asynccontextmanager
async def new_file() -> AsyncIterator[tuple[str, AsyncFile[bytes]]]:
    """Open a new file for writing in chunks; yields (key, file).

    If the block raises (too large, empty, client gone), the partial file is removed: it was
    never saved, so this is not deleting user data.
    """
    key = uuid.uuid4().hex
    root = _root()
    await anyio.to_thread.run_sync(lambda: root.mkdir(parents=True, exist_ok=True))
    path = path_for(key)
    try:
        async with await anyio.open_file(path, "wb") as out:
            yield key, out
    except BaseException:
        await anyio.to_thread.run_sync(lambda: path.unlink(missing_ok=True))
        raise
