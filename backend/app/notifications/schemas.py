import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NotificationProject(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class NotificationActor(BaseModel):
    id: uuid.UUID
    name: str


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str = Field(description="What happened, for example task.assigned. See the contract.")
    setting: str = Field(description="The setting it falls under (why you got it).")
    project: NotificationProject | None
    entity_type: str = Field(
        description="task, change_request, status_report, milestone or requirement: the link."
    )
    entity_id: uuid.UUID
    actor: NotificationActor | None = Field(description="Who did it.")
    params: dict[str, Any] = Field(
        description="Values for the text, for example code, title, fields, status."
    )
    created_at: datetime
    read_at: datetime | None


class NotificationListOut(BaseModel):
    items: list[NotificationOut] = Field(description="Newest first.")
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page; null = end.")
    unread_count: int


class UnreadCountOut(BaseModel):
    unread: int


class ReadAllOut(BaseModel):
    marked: int = Field(description="How many were unread and are now read.")


class SettingOut(BaseModel):
    key: str
    enabled: bool


class SettingsOut(BaseModel):
    settings: list[SettingOut] = Field(description="Only the settings that apply to your role.")


class SettingsUpdate(BaseModel):
    """Only the keys that change, for example {"settings": {"reports": false}}."""

    model_config = ConfigDict(extra="forbid")

    settings: dict[str, bool] = Field(max_length=20)
