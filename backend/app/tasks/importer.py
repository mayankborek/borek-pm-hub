"""Saving an import (S2-31): match users and statuses, then create the tasks in one transaction.

`csv_import.py` turns the file into rows. Here every row goes through the same `TaskCreate`
checks as the normal API, so imported data obeys the same rules. A dry run does the whole
matching and checking but writes nothing.
"""

import re
import uuid
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import has_lead_rights
from app.common.enums import (
    AttachmentKind,
    MembershipSource,
    ProjectRole,
    StatusCategory,
)
from app.core.errors import AppError
from app.projects.models import Project, ProjectMember
from app.tasks import activity, service
from app.tasks.csv_import import ImportRow, Issue, ParsedComment, ParsedFile
from app.tasks.models import Task, TaskAttachment, TaskComment, WorkflowStatus
from app.tasks.schemas import ImportIssueOut, ImportResultOut, TaskCreate
from app.users.models import User

MAX_REPORTED = 200  # problems listed in the answer; the counts are always complete
MAX_COMMENT = 5_000
BLOCKED_REASON = "Imported from Jira"

# Jira status names that are not ours -> the name of one of our default statuses. A status of
# the project with the Jira name always wins over this table.
STATUS_ALIASES = {
    "selected for development": "To do",
    "ready for development": "To do",
    "open": "To do",
    "reopened": "To do",
    "new": "To do",
    "in development": "In progress",
    "in review": "Code review",
    "review": "Code review",
    "testing/pm review": "Testing",
    "in testing": "Testing",
    "in qa": "Testing",
    "qa": "Testing",
    "on hold": "Blocked",
    "closed": "Done",
    "resolved": "Done",
    "complete": "Done",
    "completed": "Done",
    "finished": "Done",
}
# Jira's "Status category" column -> the category of one of our statuses.
CATEGORY_ALIASES = {
    "to do": StatusCategory.TODO,
    "in progress": StatusCategory.IN_PROGRESS,
    "done": StatusCategory.DONE,
}


def normalize_name(value: str) -> str:
    """Case, spaces, dots and underscores do not count: `Aida.Example` = `aida example`."""
    return " ".join(value.replace(".", " ").replace("_", " ").casefold().split())


class UserIndex:
    """Active users by e-mail and by name."""

    def __init__(self, users: list[User]) -> None:
        self._by_email = {user.email.lower(): user for user in users}
        self._by_name: dict[str, list[User]] = {}
        for user in users:
            self._by_name.setdefault(normalize_name(user.name), []).append(user)

    def find(self, row: ImportRow) -> tuple[User | None, str | None, str | None]:
        """(user, warning, missing name). A row without assignee gives no user and no warning.
        `missing name` is set when nobody matches, not when two users share the name."""
        if row.assignee_email and row.assignee_email in self._by_email:
            return self._by_email[row.assignee_email], None, None
        if not row.assignee:
            if row.assignee_email:
                message = f"'{row.assignee_email}' is not an active user; left unassigned."
                return None, message, row.assignee_email
            return None, None, None
        matches = self._by_name.get(normalize_name(row.assignee), [])
        if len(matches) == 1:
            return matches[0], None, None
        if len(matches) > 1:
            return None, f"More than one user is called '{row.assignee}'; left unassigned.", None
        return None, f"'{row.assignee}' not found; left unassigned.", row.assignee


class StatusIndex:
    """The statuses of the project, to find the one a Jira status becomes."""

    def __init__(self, statuses: list[WorkflowStatus], default: WorkflowStatus) -> None:
        self._by_name = {status.name.casefold(): status for status in statuses}
        self._first_in_category: dict[str, WorkflowStatus] = {}
        for status in statuses:  # already in position order
            self._first_in_category.setdefault(status.category, status)
        self._default = default

    def find(self, row: ImportRow) -> tuple[WorkflowStatus, str | None, bool]:
        """(status, warning, exact). `exact` is False when the name had to be translated."""
        name = (row.status or "").casefold()
        if not name:
            return self._default, None, True
        if name in self._by_name:
            return self._by_name[name], None, True
        alias = STATUS_ALIASES.get(name)
        if alias and alias.casefold() in self._by_name:
            return self._by_name[alias.casefold()], None, False
        category = CATEGORY_ALIASES.get((row.status_category or "").casefold())
        if category and category.value in self._first_in_category:
            found = self._first_in_category[category.value]
            return found, f"Status '{row.status}' not found; set to '{found.name}'.", False
        found = self._default
        return found, f"Status '{row.status}' not found; set to '{found.name}'.", False


@dataclass
class _Plan:
    row: ImportRow
    data: TaskCreate
    status: WorkflowStatus
    comments: list[ParsedComment] = field(default_factory=list)


def _order_key(row: ImportRow) -> tuple[int, int]:
    """Oldest Jira key first, so our numbers follow Jira's order. Rows without a number follow."""
    match = re.search(r"(\d+)$", row.external_key or "")
    return (int(match.group(1)) if match else 10**12, row.row)


def _comment_body(comment: ParsedComment) -> tuple[str, bool]:
    """The text to store (author and date in front, since all comments are saved under the person
    importing) and whether it had to be cut."""
    when = f" on {comment.when:%d.%m.%Y %H:%M}" if comment.when else ""
    text = f"Comment by {comment.author}{when}:\n{comment.body}"
    if len(text) <= MAX_COMMENT:
        return text, False
    return text[: MAX_COMMENT - 1].rstrip() + "…", True


def _out(issue: Issue) -> ImportIssueOut:
    return ImportIssueOut(
        row=issue.row, external_key=issue.external_key, field=issue.field, message=issue.message
    )


async def import_tasks(
    session: AsyncSession, project: Project, actor: User, parsed: ParsedFile, *, dry_run: bool
) -> ImportResultOut:
    existing = set(
        await session.scalars(
            select(Task.external_key).where(
                Task.project_id == project.id, Task.external_key.is_not(None)
            )
        )
    )
    users = UserIndex(list((await session.scalars(select(User).where(User.is_active))).all()))
    member_ids = set(
        await session.scalars(
            select(ProjectMember.user_id).where(ProjectMember.project_id == project.id)
        )
    )
    project_statuses = list(
        (
            await session.scalars(
                select(WorkflowStatus)
                .where(WorkflowStatus.project_id == project.id)
                .order_by(WorkflowStatus.position)
            )
        ).all()
    )
    statuses = StatusIndex(project_statuses, await service.default_status(session, project.id))

    failures = list(parsed.failures)
    warnings = list(parsed.warnings)
    plans: list[_Plan] = []
    skipped = 0
    seen_keys: set[str] = set()
    unknown_statuses: dict[str, str] = {}
    unknown_assignees: dict[str, None] = {}
    new_members: dict[uuid.UUID, User] = {}

    for row in parsed.rows:
        if row.external_key:
            if row.external_key in existing:
                skipped += 1
                continue
            if row.external_key in seen_keys:
                skipped += 1
                warnings.append(
                    Issue(row.row, row.external_key, "Issue key", "The key is in the file twice.")
                )
                continue

        status, status_warning, exact = statuses.find(row)
        assignee, assignee_warning, missing_assignee = users.find(row)
        is_blocked = status.category == StatusCategory.BLOCKED.value
        try:
            data = TaskCreate(
                title=row.title,
                description=row.description,
                status_id=status.id,
                priority=row.priority,
                labels=row.labels,
                start_date=row.start_date,
                due_date=row.due_date,
                estimate_value=row.estimate_value,
                estimate_unit=row.estimate_unit,
                assignee_id=assignee.id if assignee else None,
                blocked_reason=BLOCKED_REASON if is_blocked else None,
            )
        except ValidationError as error:
            first = error.errors()[0]
            column = str(first["loc"][0]) if first["loc"] else None
            message = str(first["msg"]).removeprefix("Value error, ")
            failures.append(Issue(row.row, row.external_key, column, message))
            continue

        if row.external_key:
            seen_keys.add(row.external_key)
        if row.status and not exact:
            unknown_statuses.setdefault(row.status, status.name)
        if status_warning:
            warnings.append(Issue(row.row, row.external_key, "Status", status_warning))
        if assignee_warning:
            warnings.append(Issue(row.row, row.external_key, "Assignee", assignee_warning))
        if missing_assignee:
            unknown_assignees.setdefault(missing_assignee, None)
        if assignee and assignee.id not in member_ids:
            new_members.setdefault(assignee.id, assignee)
        for comment in row.comments:
            if _comment_body(comment)[1]:
                message = f"A comment was cut to {MAX_COMMENT} characters."
                warnings.append(Issue(row.row, row.external_key, "Comment", message))
        plans.append(_Plan(row=row, data=data, status=status, comments=row.comments))

    if not dry_run:
        await _save(session, project, actor, plans, list(new_members.values()))

    warnings.sort(key=lambda issue: issue.row)
    failures.sort(key=lambda issue: issue.row)
    return ImportResultOut(
        dry_run=dry_run,
        total_rows=parsed.total_rows,
        created=len(plans),
        skipped_existing=skipped,
        failed=len(failures),
        failures=[_out(issue) for issue in failures[:MAX_REPORTED]],
        warnings=[_out(issue) for issue in warnings[:MAX_REPORTED]],
        warning_count=len(warnings),
        unknown_statuses=unknown_statuses,
        unknown_assignees=list(unknown_assignees),
        members_added=[user.name for user in new_members.values()],
        ignored_columns=parsed.ignored_columns,
        other_projects_in_file=parsed.projects if len(parsed.projects) > 1 else [],
    )


async def _save(
    session: AsyncSession,
    project: Project,
    actor: User,
    plans: list[_Plan],
    new_members: list[User],
) -> None:
    """Create everything in one transaction: all of it, or nothing."""
    if not plans:
        return
    ordered = sorted(plans, key=lambda plan: _order_key(plan.row))
    # Reserve all key numbers at once. The UPDATE locks the project row until the commit, so
    # nothing else can take a number in between (same rule as creating a single task).
    projects = Project.__table__
    last = await session.scalar(
        update(projects)  # type: ignore[arg-type]
        .where(projects.c.id == project.id)
        .values(task_counter=projects.c.task_counter + len(ordered))
        .returning(projects.c.task_counter)
    )
    assert last is not None
    first = last - len(ordered) + 1

    for user in new_members:  # D4: assignees join the project, as the import is the only way in
        role = ProjectRole.PROJECT_LEAD if has_lead_rights(user) else ProjectRole.DEVELOPER
        session.add(
            ProjectMember(
                project_id=project.id,
                user_id=user.id,
                project_role=role.value,
                source=MembershipSource.TASK_ASSIGNMENT.value,
                granted_by=actor.id,
            )
        )

    created: list[tuple[Task, _Plan]] = []
    for offset, plan in enumerate(ordered):
        data, row = plan.data, plan.row
        task = Task(
            project_id=project.id,
            key=f"{project.code}-{first + offset}",
            external_key=row.external_key,
            title=data.title,
            description=data.description,
            priority=data.priority.value,
            labels=data.labels,
            start_date=data.start_date,
            due_date=data.due_date,
            estimate_value=data.estimate_value,
            estimate_unit=data.estimate_unit.value if data.estimate_unit else None,
            assignee_id=data.assignee_id,
            created_by=actor.id,
        )
        if row.created_at:
            task.created_at = row.created_at  # keep Jira's date so age and order stay true
        service.apply_status(task, plan.status, data.blocked_reason)
        if row.resolved_at and plan.status.category == StatusCategory.DONE.value:
            task.completed_at = row.resolved_at
        session.add(task)
        created.append((task, plan))

    try:
        await session.flush()
        for task, plan in created:
            key = plan.row.external_key
            activity.record(
                session,
                task.id,
                actor.id,
                "imported",
                {"external_key": [None, key]} if key else None,
            )
            for comment in plan.comments:
                saved = TaskComment(
                    task_id=task.id, author_id=actor.id, body=_comment_body(comment)[0]
                )
                if comment.when:
                    saved.created_at = comment.when
                session.add(saved)
            for attachment in plan.row.attachments:
                session.add(
                    TaskAttachment(
                        task_id=task.id,
                        kind=AttachmentKind.LINK.value,
                        name=attachment.name,
                        url=attachment.url,
                        uploaded_by=actor.id,
                    )
                )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError(
            409,
            "CONFLICT",
            "The import clashed with another change. Nothing was saved. Run it again.",
        ) from None
