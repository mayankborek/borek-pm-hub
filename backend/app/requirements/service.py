"""Requirements and client acceptance. Routers check permissions; rules live here.

A requirement starts as a draft (version 1). The project lead or a Manager publishes the newest
version for acceptance; the client answers that exact version: accepted, changes requested or
rejected. After "changes requested" the lead edits (which starts a new draft version) and
publishes again. Accepted and rejected are final. Publishing a new version while the client has
not answered the previous one supersedes it: the client can only answer the newest published
version. Published versions never change, so an answer always refers to what the client saw.
"""

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.common.enums import ProjectType
from app.core.errors import AppError
from app.milestones.models import Milestone
from app.milestones.service import check_milestone
from app.notifications import events as notifications
from app.organisations.schemas import PersonBrief
from app.projects.models import Project, ProjectMember
from app.requirements.models import (
    CLOSED,
    AcceptanceDecision,
    Requirement,
    RequirementStatus,
    RequirementVersion,
)
from app.requirements.schemas import (
    ClientMilestoneLink,
    ClientRequirementOut,
    ClientRequirementResponse,
    ClientRequirementVersionOut,
    MilestoneBrief,
    RequirementCreate,
    RequirementOut,
    RequirementUpdate,
    RequirementVersionOut,
    VersionState,
)
from app.users.models import User

CONTENT_FIELDS = ("description", "acceptance_criteria", "change_note")


def _not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Requirement not found.")


def _version_conflict() -> AppError:
    return AppError(409, "VERSION_CONFLICT", "The requirement was changed by someone else. Reload.")


def _closed() -> AppError:
    return AppError(
        409,
        "REQUIREMENT_CLOSED",
        "The requirement is already accepted or rejected. Raise a change request instead.",
    )


def _invalid(field: str, issue: str, message: str) -> AppError:
    return AppError(
        422,
        "VALIDATION_ERROR",
        "The request is not valid.",
        [{"field": field, "issue": issue, "message": message}],
    )


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise _version_conflict() from None


def _touch(requirement: Requirement) -> None:
    """Make the requirement row change, so its optimistic-lock version moves on as well."""
    requirement.updated_at = datetime.now(UTC)


# --- reading ------------------------------------------------------------------------------------


async def _versions(
    session: AsyncSession, requirement_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[RequirementVersion]]:
    """Per requirement, newest version first."""
    out: dict[uuid.UUID, list[RequirementVersion]] = {rid: [] for rid in requirement_ids}
    if requirement_ids:
        rows = await session.scalars(
            select(RequirementVersion)
            .where(RequirementVersion.requirement_id.in_(requirement_ids))
            .order_by(RequirementVersion.requirement_id, RequirementVersion.number.desc())
        )
        for v in rows:
            out[v.requirement_id].append(v)
    return out


def _newest_published(versions: list[RequirementVersion]) -> RequirementVersion | None:
    return next((v for v in versions if v.published_at is not None), None)


def _state(v: RequirementVersion, newest_published: RequirementVersion | None) -> VersionState:
    if v.published_at is None:
        return "draft"
    if v.response is not None:
        return "answered"
    return "awaiting_answer" if v is newest_published else "superseded"


async def _people(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    return {u.id: u for u in await session.scalars(select(User).where(User.id.in_(ids)))}


async def _milestones(
    session: AsyncSession, requirements: list[Requirement]
) -> dict[uuid.UUID, Milestone]:
    ids = {r.milestone_id for r in requirements if r.milestone_id}
    if not ids:
        return {}
    return {m.id: m for m in await session.scalars(select(Milestone).where(Milestone.id.in_(ids)))}


async def requirements_out(
    session: AsyncSession, requirements: list[Requirement]
) -> list[RequirementOut]:
    versions = await _versions(session, [r.id for r in requirements])
    ids: set[uuid.UUID] = set()
    for r in requirements:
        ids |= {r.created_by} | ({r.owner_id} if r.owner_id else set())
        for v in versions[r.id]:
            ids |= {x for x in (v.created_by, v.published_by, v.responded_by) if x}
    users = await _people(session, ids)
    milestones = await _milestones(session, requirements)

    def person(user_id: uuid.UUID | None) -> PersonBrief | None:
        user = users.get(user_id) if user_id else None
        return PersonBrief(id=user.id, name=user.name, email=user.email) if user else None

    out = []
    for r in requirements:
        mine = versions[r.id]
        published = _newest_published(mine)
        m = milestones.get(r.milestone_id) if r.milestone_id else None
        creator = person(r.created_by)
        assert creator is not None and mine
        version_out = []
        for v in mine:
            created_by = person(v.created_by)
            assert created_by is not None
            version_out.append(
                RequirementVersionOut(
                    number=v.number,
                    state=_state(v, published),
                    description=v.description,
                    acceptance_criteria=list(v.acceptance_criteria),
                    change_note=v.change_note,
                    created_by=created_by,
                    created_at=v.created_at,
                    published_at=v.published_at,
                    published_by=person(v.published_by),
                    response=AcceptanceDecision(v.response) if v.response else None,
                    response_comment=v.response_comment,
                    responded_by=person(v.responded_by),
                    responded_at=v.responded_at,
                )
            )
        out.append(
            RequirementOut(
                id=r.id,
                project_id=r.project_id,
                code=r.code,
                title=r.title,
                owner=person(r.owner_id),
                milestone=(
                    MilestoneBrief(id=m.id, code=m.code, name=m.name, due_date=m.due_date)
                    if m
                    else None
                ),
                status=RequirementStatus(r.status),
                current_version=mine[0].number,
                published_version=published.number if published else None,
                has_unpublished_changes=published is not None and mine[0].published_at is None,
                versions=version_out,
                created_by=creator,
                version=r.version,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return out


def _counts(rows: list[Requirement], statuses: list[RequirementStatus]) -> dict[str, int]:
    per_status: Counter[str] = Counter(r.status for r in rows)
    return {"total": len(rows), **{s.value: per_status.get(s.value, 0) for s in statuses}}


async def list_requirements(
    session: AsyncSession, project_id: uuid.UUID, status: RequirementStatus | None = None
) -> tuple[list[Requirement], dict[str, int]]:
    """Not archived, by code, and counts per status over all of them."""
    rows = list(
        await session.scalars(
            select(Requirement)
            .where(Requirement.project_id == project_id, Requirement.archived_at.is_(None))
            .order_by(Requirement.code)
        )
    )
    counts = _counts(rows, list(RequirementStatus))
    if status is not None:
        rows = [r for r in rows if r.status == status.value]
    return rows, counts


async def get_requirement(
    session: AsyncSession, project_id: uuid.UUID, requirement_id: uuid.UUID
) -> Requirement:
    found = await session.get(Requirement, requirement_id)
    if found is None or found.project_id != project_id or found.archived_at is not None:
        raise _not_found()
    return found


# --- writing ------------------------------------------------------------------------------------


async def _check_owner(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    member = await session.scalar(
        select(ProjectMember.id)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            User.is_active.is_(True),
        )
    )
    if member is None:
        raise _invalid("owner_id", "not_a_member", "The owner must be an active project member.")


async def _next_code(session: AsyncSession, project_id: uuid.UUID) -> str:
    # Lock the project row so two requirements created at once never get the same code.
    await session.execute(select(Project.id).where(Project.id == project_id).with_for_update())
    used = await session.scalar(
        select(func.count(Requirement.id)).where(Requirement.project_id == project_id)
    )
    return f"REQ-{(used or 0) + 1:02d}"


async def create_requirement(
    session: AsyncSession, actor: User, project_id: uuid.UUID, data: RequirementCreate
) -> Requirement:
    if data.owner_id:
        await _check_owner(session, project_id, data.owner_id)
    if data.milestone_id:
        await check_milestone(session, project_id, data.milestone_id)
    requirement = Requirement(
        project_id=project_id,
        code=await _next_code(session, project_id),
        title=data.title,
        owner_id=data.owner_id,
        milestone_id=data.milestone_id,
        created_by=actor.id,
    )
    session.add(requirement)
    await session.flush()
    session.add(
        RequirementVersion(
            requirement_id=requirement.id,
            number=1,
            description=data.description,
            acceptance_criteria=data.acceptance_criteria,
            created_by=actor.id,
        )
    )
    record_audit(
        session,
        actor,
        "requirement.created",
        "requirement",
        requirement.id,
        project_id=project_id,
        after={"code": requirement.code, "title": requirement.title},
    )
    await session.commit()
    await session.refresh(requirement)
    return requirement


async def update_requirement(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    data: RequirementUpdate,
) -> Requirement:
    requirement = await get_requirement(session, project_id, requirement_id)
    if requirement.status in CLOSED:
        raise _closed()
    if data.version != requirement.version:
        raise _version_conflict()
    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    if changes.get("owner_id"):
        await _check_owner(session, project_id, changes["owner_id"])
    if changes.get("milestone_id"):
        await check_milestone(session, project_id, changes["milestone_id"])
    for field in ("title", "owner_id", "milestone_id"):
        if field in changes:
            setattr(requirement, field, changes[field])

    new_version: int | None = None
    if any(field in changes for field in CONTENT_FIELDS):
        latest = (await _versions(session, [requirement.id]))[requirement.id][0]
        description = changes.get("description", latest.description)
        criteria = changes.get("acceptance_criteria", list(latest.acceptance_criteria))
        if latest.published_at is None:
            latest.description = description
            latest.acceptance_criteria = criteria
            if "change_note" in changes:
                latest.change_note = changes["change_note"]
        elif description != latest.description or criteria != list(latest.acceptance_criteria):
            # Published versions never change: the edit becomes the next draft version.
            new_version = latest.number + 1
            session.add(
                RequirementVersion(
                    requirement_id=requirement.id,
                    number=new_version,
                    description=description,
                    acceptance_criteria=criteria,
                    change_note=changes.get("change_note"),
                    created_by=actor.id,
                )
            )
        else:
            raise _invalid(
                "description",
                "no_change",
                "The published version already has this content. Change the description or "
                "the acceptance criteria to start a new version.",
            )
    _touch(requirement)
    after: dict[str, object] = {"changed": sorted(changes)}
    if new_version:
        after["new_version"] = new_version
    record_audit(
        session,
        actor,
        "requirement.updated",
        "requirement",
        requirement.id,
        project_id=project_id,
        after=after,
    )
    await _commit(session)
    await session.refresh(requirement)
    return requirement


async def publish(
    session: AsyncSession,
    actor: User,
    project: Project,
    requirement_id: uuid.UUID,
    version: int,
) -> Requirement:
    """Send the newest (draft) version to the client for acceptance."""
    requirement = await get_requirement(session, project.id, requirement_id)
    if requirement.status in CLOSED:
        raise _closed()
    if version != requirement.version:
        raise _version_conflict()
    if project.project_type != ProjectType.EXTERNAL.value or project.client_organisation_id is None:
        raise AppError(
            409,
            "NO_CLIENT",
            "Only external projects with a client can publish requirements for acceptance.",
        )
    latest = (await _versions(session, [requirement.id]))[requirement.id][0]
    if latest.published_at is not None:
        raise AppError(
            409,
            "NOTHING_TO_PUBLISH",
            f"Version {latest.number} is already published. Edit the requirement to start a "
            "new version.",
        )
    if not latest.acceptance_criteria:
        raise _invalid(
            "acceptance_criteria",
            "required",
            "Add at least one acceptance criterion before publishing.",
        )
    latest.published_at = datetime.now(UTC)
    latest.published_by = actor.id
    requirement.status = RequirementStatus.AWAITING_ACCEPTANCE.value
    record_audit(
        session,
        actor,
        "requirement.published",
        "requirement",
        requirement.id,
        project_id=project.id,
        after={"code": requirement.code, "version": latest.number},
    )
    await notifications.requirement_published(session, actor, requirement, latest.number)
    await _commit(session)
    await session.refresh(requirement)
    return requirement


async def archive(
    session: AsyncSession, actor: User, project_id: uuid.UUID, requirement_id: uuid.UUID
) -> None:
    """Hidden everywhere afterwards, the client portal included; the code is not reused."""
    requirement = await get_requirement(session, project_id, requirement_id)
    requirement.archived_at = datetime.now(UTC)
    record_audit(
        session,
        actor,
        "requirement.archived",
        "requirement",
        requirement.id,
        project_id=project_id,
        after={"code": requirement.code},
    )
    await _commit(session)


# --- client side --------------------------------------------------------------------------------

CLIENT_STATUSES: list[RequirementStatus] = [
    s for s in RequirementStatus if s is not RequirementStatus.DRAFT
]


async def client_requirements(session: AsyncSession, project_id: uuid.UUID) -> list[Requirement]:
    """What the client sees: not archived and published at least once, by code."""
    return list(
        await session.scalars(
            select(Requirement)
            .where(
                Requirement.project_id == project_id,
                Requirement.archived_at.is_(None),
                Requirement.status != RequirementStatus.DRAFT.value,
            )
            .order_by(Requirement.code)
        )
    )


def client_counts(rows: list[Requirement]) -> dict[str, int]:
    return _counts(rows, CLIENT_STATUSES)


async def client_requirement(
    session: AsyncSession, project_id: uuid.UUID, requirement_id: uuid.UUID
) -> Requirement:
    found = await get_requirement(session, project_id, requirement_id)
    if found.status == RequirementStatus.DRAFT.value:
        raise _not_found()
    return found


async def awaiting_answer_count(session: AsyncSession, project_ids: list[uuid.UUID]) -> int:
    """Requirements whose current version waits for the client ("Awaiting your input")."""
    if not project_ids:
        return 0
    return (
        await session.scalar(
            select(func.count(Requirement.id)).where(
                Requirement.project_id.in_(project_ids),
                Requirement.archived_at.is_(None),
                Requirement.status == RequirementStatus.AWAITING_ACCEPTANCE.value,
            )
        )
        or 0
    )


def _client_state(
    v: RequirementVersion, newest: RequirementVersion
) -> Literal["awaiting_answer", "answered", "superseded"]:
    if v.response is not None:
        return "answered"
    return "awaiting_answer" if v is newest else "superseded"


async def client_out(
    session: AsyncSession, requirements: list[Requirement]
) -> list[ClientRequirementOut]:
    """Only published versions; drafts, internal people's emails and hidden milestones stay
    out."""
    versions = await _versions(session, [r.id for r in requirements])
    ids: set[uuid.UUID] = set()
    for r in requirements:
        ids |= {r.owner_id} if r.owner_id else set()
        for v in versions[r.id]:
            ids |= {x for x in (v.published_by, v.responded_by) if x}
    users = await _people(session, ids)
    milestones = await _milestones(session, requirements)

    def name(user_id: uuid.UUID | None) -> str | None:
        user = users.get(user_id) if user_id else None
        return user.name if user else None

    out = []
    for r in requirements:
        published = [v for v in versions[r.id] if v.published_at is not None]
        newest = published[0]  # the client only gets requirements that were published
        shown = [
            ClientRequirementVersionOut(
                number=v.number,
                state=_client_state(v, newest),
                description=v.description,
                acceptance_criteria=list(v.acceptance_criteria),
                change_note=v.change_note,
                published_at=v.published_at,
                published_by=name(v.published_by),
                response=AcceptanceDecision(v.response) if v.response else None,
                response_comment=v.response_comment,
                responded_by=name(v.responded_by),
                responded_at=v.responded_at,
            )
            for v in published
        ]
        m = milestones.get(r.milestone_id) if r.milestone_id else None
        out.append(
            ClientRequirementOut(
                id=r.id,
                code=r.code,
                title=r.title,
                status=RequirementStatus(r.status),
                awaiting_your_answer=r.status == RequirementStatus.AWAITING_ACCEPTANCE.value,
                owner=name(r.owner_id),
                milestone=(
                    ClientMilestoneLink(code=m.code, name=m.name)
                    if m and m.client_visible and m.archived_at is None
                    else None
                ),
                current=shown[0],
                history=shown[1:],
            )
        )
    return out


async def respond(
    session: AsyncSession,
    actor: User,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    data: ClientRequirementResponse,
) -> Requirement:
    """The client's answer to the newest published version; the first answer counts."""
    requirement = await session.get(Requirement, requirement_id, with_for_update=True)
    if (
        requirement is None
        or requirement.project_id != project_id
        or requirement.archived_at is not None
        or requirement.status == RequirementStatus.DRAFT.value
    ):
        raise _not_found()
    newest = _newest_published((await _versions(session, [requirement.id]))[requirement.id])
    assert newest is not None
    if requirement.status != RequirementStatus.AWAITING_ACCEPTANCE.value:
        raise AppError(
            409, "NOT_AWAITING_ANSWER", "This requirement is not waiting for your answer."
        )
    if data.version_number != newest.number:
        raise AppError(
            409,
            "VERSION_NOT_OPEN",
            f"Version {data.version_number} cannot be answered. Review version {newest.number}.",
        )
    newest.response = data.decision.value
    newest.response_comment = data.comment
    newest.responded_by = actor.id
    newest.responded_at = datetime.now(UTC)
    requirement.status = data.decision.value
    record_audit(
        session,
        actor,
        f"requirement.{data.decision.value}",
        "requirement",
        requirement.id,
        project_id=project_id,
        after={"code": requirement.code, "version": newest.number},
    )
    await notifications.requirement_answered(
        session, actor, requirement, newest.number, data.decision.value
    )
    await _commit(session)
    await session.refresh(requirement)
    return requirement
