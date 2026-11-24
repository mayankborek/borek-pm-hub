import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.task_links.models import LinkType
from app.tasks.schemas import StatusBrief, UserBrief


class LinkKind(StrEnum):
    """How a link reads from the task you are on."""

    BLOCKS = "blocks"
    IS_BLOCKED_BY = "is_blocked_by"
    RELATES_TO = "relates_to"
    DUPLICATES = "duplicates"
    IS_DUPLICATED_BY = "is_duplicated_by"
    CLONES = "clones"
    IS_CLONED_BY = "is_cloned_by"


# kind -> (stored type, this task is the source)
KINDS: dict[LinkKind, tuple[LinkType, bool]] = {
    LinkKind.BLOCKS: (LinkType.BLOCKS, True),
    LinkKind.IS_BLOCKED_BY: (LinkType.BLOCKS, False),
    LinkKind.RELATES_TO: (LinkType.RELATES_TO, True),
    LinkKind.DUPLICATES: (LinkType.DUPLICATES, True),
    LinkKind.IS_DUPLICATED_BY: (LinkType.DUPLICATES, False),
    LinkKind.CLONES: (LinkType.CLONES, True),
    LinkKind.IS_CLONED_BY: (LinkType.CLONES, False),
}
LABELS: dict[LinkKind, str] = {
    LinkKind.BLOCKS: "blocks",
    LinkKind.IS_BLOCKED_BY: "is blocked by",
    LinkKind.RELATES_TO: "relates to",
    LinkKind.DUPLICATES: "duplicates",
    LinkKind.IS_DUPLICATED_BY: "is duplicated by",
    LinkKind.CLONES: "clones",
    LinkKind.IS_CLONED_BY: "is cloned by",
}


def kind_of(link_type: str, is_source: bool) -> LinkKind:
    for kind, (stored, source) in KINDS.items():
        if stored.value == link_type and (source == is_source or stored is LinkType.RELATES_TO):
            return kind
    raise ValueError(link_type)


class LinkIn(BaseModel):
    """Link this task to another task of the same project. Find it with
    `GET /projects/{id}/tasks?q=` (key or title)."""

    model_config = ConfigDict(extra="forbid")

    kind: LinkKind
    task_id: uuid.UUID = Field(description="The other task.")


class LinkedTask(BaseModel):
    id: uuid.UUID
    key: str
    title: str
    status: StatusBrief
    assignee: UserBrief | None


class TaskLinkOut(BaseModel):
    id: uuid.UUID
    kind: LinkKind
    label: str = Field(description='Readable, e.g. "is blocked by".')
    task: LinkedTask
    created_by: UserBrief
    created_at: datetime
