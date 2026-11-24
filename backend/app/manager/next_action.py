"""Delivery cards (BB-14): the one thing to look at next on a project.

Picked per project, first match wins (Mayank 24.11.2026):
1. an overdue milestone (open, due date passed; the oldest),
2. a change request waiting for a decision (pending or in review; the oldest),
3. a requirement waiting for the client's acceptance (the longest waiting),
4. the next open milestone.
Change requests count only where the reader may see them (leads, Managers, the client's AM).
"""

import uuid
from collections.abc import Iterable
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.change_requests.models import ChangeRequest, ChangeRequestStatus
from app.manager.service import _open_milestones
from app.milestones.schemas import MilestoneState
from app.requirements.models import Requirement, RequirementStatus


class NextActionKind(StrEnum):
    OVERDUE_MILESTONE = "overdue_milestone"
    CHANGE_REQUEST = "change_request"  # waiting for a decision
    CLIENT_ACCEPTANCE = "client_acceptance"  # a requirement waiting for the client
    NEXT_MILESTONE = "next_milestone"


class NextAction(BaseModel):
    kind: NextActionKind
    entity_id: uuid.UUID = Field(description="Milestone, change request or requirement id.")
    code: str = Field(description="M-01, CR-01 or REQ-01.")
    title: str
    due_date: date | None = Field(description="Milestones only.")
    status: str = Field(description="Milestone state, change request or requirement status.")


async def next_actions(
    session: AsyncSession,
    project_ids: list[uuid.UUID],
    *,
    change_requests_for: Iterable[uuid.UUID],
) -> dict[uuid.UUID, NextAction]:
    """`change_requests_for`: the projects whose change requests the reader may see."""
    if not project_ids:
        return {}
    found: dict[uuid.UUID, NextAction] = {}
    milestones = await _open_milestones(session, project_ids)  # by due date
    for m in milestones:
        if m.state == MilestoneState.LATE and m.project_id not in found:
            found[m.project_id] = NextAction(
                kind=NextActionKind.OVERDUE_MILESTONE,
                entity_id=m.id,
                code=m.code,
                title=m.name,
                due_date=m.due_date,
                status=m.state.value,
            )
    cr_projects = [p for p in set(change_requests_for) & set(project_ids) if p not in found]
    if cr_projects:
        rows = await session.scalars(
            select(ChangeRequest)
            .where(
                ChangeRequest.project_id.in_(cr_projects),
                ChangeRequest.status.in_(
                    [ChangeRequestStatus.PENDING.value, ChangeRequestStatus.IN_REVIEW.value]
                ),
            )
            .order_by(ChangeRequest.created_at)
        )
        for cr in rows:
            found.setdefault(
                cr.project_id,
                NextAction(
                    kind=NextActionKind.CHANGE_REQUEST,
                    entity_id=cr.id,
                    code=cr.code,
                    title=cr.title,
                    due_date=None,
                    status=cr.status,
                ),
            )
    waiting = [p for p in project_ids if p not in found]
    if waiting:
        rows = await session.scalars(
            select(Requirement)
            .where(
                Requirement.project_id.in_(waiting),
                Requirement.archived_at.is_(None),
                Requirement.status == RequirementStatus.AWAITING_ACCEPTANCE.value,
            )
            .order_by(Requirement.updated_at)
        )
        for r in rows:
            found.setdefault(
                r.project_id,
                NextAction(
                    kind=NextActionKind.CLIENT_ACCEPTANCE,
                    entity_id=r.id,
                    code=r.code,
                    title=r.title,
                    due_date=None,
                    status=r.status,
                ),
            )
    for m in milestones:
        if m.project_id not in found:
            found[m.project_id] = NextAction(
                kind=NextActionKind.NEXT_MILESTONE,
                entity_id=m.id,
                code=m.code,
                title=m.name,
                due_date=m.due_date,
                status=m.state.value,
            )
    return found
