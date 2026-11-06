import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditPerson(BaseModel):
    id: uuid.UUID
    name: str
    email: str


class AuditEventOut(BaseModel):
    id: uuid.UUID
    at: datetime
    actor: AuditPerson | None
    action: str
    entity_type: str
    entity_id: uuid.UUID
    project_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    request_id: str | None


class AuditEventListOut(BaseModel):
    items: list[AuditEventOut]
    total: int
    page: int
    page_size: int
