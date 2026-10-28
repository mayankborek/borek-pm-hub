"""Request and response shapes for comments, attachments and history (F08)."""

import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.validation import clean_optional_text, clean_text, has_control_chars
from app.tasks.schemas import UserBrief


def _clean_body(value: str) -> str:
    return clean_text(value, label="The comment", multiline=True)


class CommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=5000)

    _strip = field_validator("body")(_clean_body)


class CommentOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    author: UserBrief
    body: str
    created_at: datetime
    edited_at: datetime | None


class LinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=255, description="Defaults to the host.")

    @field_validator("url")
    @classmethod
    def _http_only(cls, value: str) -> str:
        value = value.strip()
        if has_control_chars(value) or any(char.isspace() for char in value):
            raise ValueError("The link contains characters that are not allowed.")
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("The link must start with http:// or https://.")
        if parts.username is not None or parts.password is not None:
            raise ValueError("The link must not contain a user name or password.")
        return value

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        return clean_optional_text(value, max_length=255, label="Name", multiline=False)


class AttachmentOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    kind: str = Field(description="'file' (stored by us) or 'link' (URL only).")
    name: str
    url: str | None = Field(description="Links only.")
    download_url: str | None = Field(description="Files only; needs the same auth as the API.")
    content_type: str | None
    size_bytes: int | None
    uploaded_by: UserBrief
    created_at: datetime


class ActivityOut(BaseModel):
    id: uuid.UUID
    action: str = Field(
        description="created, updated, archived, commented, attachment_added, attachment_removed"
    )
    actor: UserBrief
    changes: dict[str, list[Any]] = Field(description='{"field": [old, new]}, readable values.')
    created_at: datetime


class ActivityListOut(BaseModel):
    items: list[ActivityOut]
    total: int
    page: int
    page_size: int
