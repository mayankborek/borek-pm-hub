"""Role permissions matrix and per-person project switches (Administrator handoff 10 + 11).

Only differences from the defaults are stored; saving a default value deletes the row, so a
reset is a delete. Every change is audited with the previous and the new value.
"""

import uuid
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.access_policy.models import ProjectPermissionSetting, RolePermissionSetting
from app.access_policy.schemas import (
    ControlOut,
    PersonProjectAccessOut,
    PersonProjectOut,
    PersonProjectsOut,
    PersonRef,
    ProjectRef,
    RoleCellOut,
    RoleColumnOut,
    RoleMatrixOut,
    SectionOut,
)
from app.audit.service import record_audit
from app.auth.permissions import Action, Resource, can, is_admin, is_client, sees_all_projects
from app.auth.policy import (
    CONFIGURABLE_ROLES,
    MATRIX_ROLES,
    PROJECT_CONTROL_KEYS,
    PROJECT_CONTROLS,
    PROJECT_SECTIONS,
    ROLE_PERMISSION_KEYS,
    ROLE_PERMISSIONS,
    SECTION_KEYS,
    attach_role_policy,
    role_value,
)
from app.common.enums import GLOBAL_ROLE_LABELS, GlobalRole, ProjectRole
from app.core.errors import AppError
from app.projects.membership import ProjectAccess, project_access, visible_project_ids
from app.projects.models import Project
from app.users.models import User

# --- screen 11: role matrix ----------------------------------------------------------------------


async def _role_settings(session: AsyncSession) -> dict[str, dict[str, bool]]:
    found: dict[str, dict[str, bool]] = defaultdict(dict)
    rows = await session.execute(
        select(
            RolePermissionSetting.role,
            RolePermissionSetting.permission,
            RolePermissionSetting.enabled,
        )
    )
    for role, permission, enabled in rows.all():
        found[role][permission] = enabled
    return found


async def role_matrix(session: AsyncSession) -> RoleMatrixOut:
    saved = await _role_settings(session)
    columns = []
    for role in MATRIX_ROLES:
        overrides = saved.get(role.value, {})
        cells = [
            RoleCellOut(
                key=p.key,
                label=p.label,
                section=p.section,
                value=role_value(role, p.key, overrides),
                default=p.defaults[role],
                editable=role in CONFIGURABLE_ROLES and p.defaults[role] in ("on", "off"),
            )
            for p in ROLE_PERMISSIONS
        ]
        columns.append(
            RoleColumnOut(
                role=role.value,
                label=GLOBAL_ROLE_LABELS[role],
                editable=role in CONFIGURABLE_ROLES,
                customised=any(c.value != c.default for c in cells),
                permissions=cells,
            )
        )
    return RoleMatrixOut(roles=columns)


def _role_entity(role: GlobalRole) -> uuid.UUID:
    """A stable id for a role in the audit log (roles have no table)."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"borek-pm-hub:role:{role.value}")


def _configurable_role(role: str) -> GlobalRole:
    try:
        value = GlobalRole(role)
    except ValueError:
        raise AppError(404, "NOT_FOUND", "Role not found.") from None
    if value not in CONFIGURABLE_ROLES:
        raise AppError(409, "FIXED_POLICY", "This role's permissions are fixed.")
    return value


async def set_role_permission(
    session: AsyncSession, actor: User, role: str, key: str, enabled: bool
) -> RoleMatrixOut:
    value = _configurable_role(role)
    permission = ROLE_PERMISSION_KEYS.get(key)
    if permission is None:
        raise AppError(404, "NOT_FOUND", "Permission not found.")
    default = permission.defaults[value]
    if default not in ("on", "off"):
        raise AppError(409, "FIXED_POLICY", "This cell cannot be changed.")
    saved = (await _role_settings(session)).get(value.value, {})
    before = role_value(value, key, saved) == "on"
    await session.execute(
        delete(RolePermissionSetting).where(
            RolePermissionSetting.role == value.value, RolePermissionSetting.permission == key
        )
    )
    if enabled != (default == "on"):
        session.add(
            RolePermissionSetting(
                role=value.value, permission=key, enabled=enabled, updated_by=actor.id
            )
        )
    if before != enabled:
        record_audit(
            session,
            actor,
            "access_policy.role_changed",
            "role",
            _role_entity(value),
            before={"role": value.value, key: before},
            after={"role": value.value, key: enabled},
        )
    await session.commit()
    return await role_matrix(session)


async def reset_role(session: AsyncSession, actor: User, role: str) -> RoleMatrixOut:
    value = _configurable_role(role)
    saved = (await _role_settings(session)).get(value.value, {})
    if saved:
        await session.execute(
            delete(RolePermissionSetting).where(RolePermissionSetting.role == value.value)
        )
        record_audit(
            session,
            actor,
            "access_policy.role_reset",
            "role",
            _role_entity(value),
            before={"role": value.value, **saved},
            after={"role": value.value},
        )
        await session.commit()
    return await role_matrix(session)


# --- screen 10: a person's switches per project --------------------------------------------------


async def _person(session: AsyncSession, user_id: uuid.UUID) -> User:
    person = await session.get(User, user_id)
    if person is None:
        raise AppError(404, "NOT_FOUND", "User not found.")
    rows = await session.execute(
        select(RolePermissionSetting.permission, RolePermissionSetting.enabled).where(
            RolePermissionSetting.role == person.global_role
        )
    )
    attach_role_policy(person, {permission: enabled for permission, enabled in rows.all()})
    return person


def _person_ref(person: User) -> PersonRef:
    return PersonRef(id=person.id, name=person.name, email=person.email, role=person.global_role)


def _editable_person(person: User) -> bool:
    return person.is_active and not is_admin(person) and not is_client(person)


def _access_kind(person: User, access: ProjectAccess) -> str:
    if access.is_project_lead:
        return ProjectRole.PROJECT_LEAD.value
    if access.is_member:
        return ProjectRole.DEVELOPER.value
    if access.is_account_manager:
        return "account_manager"
    return "manager"


def _reaches(person: User, access: ProjectAccess) -> bool:
    return access.is_member or access.is_account_manager or sees_all_projects(person)


async def _customised_projects(session: AsyncSession, person: User) -> set[uuid.UUID]:
    return set(
        await session.scalars(
            select(ProjectPermissionSetting.project_id).where(
                ProjectPermissionSetting.user_id == person.id
            )
        )
    )


async def person_projects(session: AsyncSession, user_id: uuid.UUID) -> PersonProjectsOut:
    """The person's active projects ("All" on screen 10)."""
    person = await _person(session, user_id)
    items: list[PersonProjectOut] = []
    if _editable_person(person):
        query = select(Project).where(Project.archived_at.is_(None))
        if not sees_all_projects(person):
            query = query.where(Project.id.in_(visible_project_ids(person)))
        customised = await _customised_projects(session, person)
        for project in await session.scalars(query.order_by(Project.code)):
            access = await project_access(session, person, project)
            items.append(
                PersonProjectOut(
                    id=project.id,
                    code=project.code,
                    name=project.name,
                    access=_access_kind(person, access),
                    customised=project.id in customised,
                )
            )
    return PersonProjectsOut(
        person=_person_ref(person), editable=_editable_person(person), items=items
    )


async def _project_for(
    session: AsyncSession, person: User, project_id: uuid.UUID
) -> tuple[Project, ProjectAccess]:
    project = await session.get(Project, project_id)
    if project is None or project.archived_at is not None:
        raise AppError(404, "NOT_FOUND", "Project not found.")
    access = await project_access(session, person, project)
    if not _editable_person(person) or not _reaches(person, access):
        raise AppError(
            409,
            "NO_PROJECT_ACCESS",
            "This person has no access to the project, so there is nothing to change. "
            "Reload the list.",
        )
    return project, access


async def _saved(session: AsyncSession, person: User, project: Project) -> dict[str, bool]:
    rows = await session.execute(
        select(ProjectPermissionSetting.permission, ProjectPermissionSetting.enabled).where(
            ProjectPermissionSetting.project_id == project.id,
            ProjectPermissionSetting.user_id == person.id,
        )
    )
    return {permission: enabled for permission, enabled in rows.all()}


def _default(person: User, project: Project, access: ProjectAccess, action: str) -> bool:
    plain = Resource(
        project_id=project.id,
        is_member=access.is_member,
        is_project_lead=access.is_project_lead,
        is_account_manager=access.is_account_manager,
    )
    return can(person, Action(action), plain)


async def person_project_access(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> PersonProjectAccessOut:
    person = await _person(session, user_id)
    project, access = await _project_for(session, person, project_id)
    saved = await _saved(session, person, project)
    resource = access.resource(project.id)
    by_action: dict[str, list[str]] = defaultdict(list)
    for control in PROJECT_CONTROLS:
        if control.action:
            by_action[control.action].append(control.key)
    sections = []
    for section in PROJECT_SECTIONS:
        controls = []
        for control in (c for c in PROJECT_CONTROLS if c.section == section.key):
            if control.action is None:
                controls.append(
                    ControlOut(
                        key=control.key,
                        label=control.label,
                        enabled=can(person, Action.PROJECT_VIEW, resource),
                        default=_default(person, project, access, Action.PROJECT_VIEW.value),
                        customised=False,
                        editable=False,
                        linked_with=[],
                    )
                )
                continue
            controls.append(
                ControlOut(
                    key=control.key,
                    label=control.label,
                    enabled=can(person, Action(control.action), resource),
                    default=_default(person, project, access, control.action),
                    customised=control.key in saved,
                    editable=True,
                    linked_with=[k for k in by_action[control.action] if k != control.key],
                )
            )
        sections.append(
            SectionOut(
                key=section.key,
                label=section.label,
                customised=any(c.customised for c in controls),
                controls=controls,
            )
        )
    return PersonProjectAccessOut(
        person=_person_ref(person),
        project=ProjectRef(id=project.id, code=project.code, name=project.name),
        access=_access_kind(person, access),
        sections=sections,
    )


async def set_project_control(
    session: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    key: str,
    enabled: bool,
) -> PersonProjectAccessOut:
    """Save at once (no Save button in the design). Linked controls (same server right) change
    together so the screen never shows two answers for one right."""
    control = PROJECT_CONTROL_KEYS.get(key)
    if control is None:
        raise AppError(404, "NOT_FOUND", "Permission not found.")
    if control.action is None:
        raise AppError(409, "FIXED_POLICY", "This control follows another one.")
    person = await _person(session, user_id)
    project, access = await _project_for(session, person, project_id)
    linked = [c.key for c in PROJECT_CONTROLS if c.action == control.action]
    before = await _saved(session, person, project)
    await session.execute(
        delete(ProjectPermissionSetting).where(
            ProjectPermissionSetting.project_id == project.id,
            ProjectPermissionSetting.user_id == person.id,
            ProjectPermissionSetting.permission.in_(linked),
        )
    )
    if enabled != _default(person, project, access, control.action):
        await session.execute(
            insert(ProjectPermissionSetting).values(
                [
                    {
                        "project_id": project.id,
                        "user_id": person.id,
                        "permission": k,
                        "enabled": enabled,
                        "updated_by": actor.id,
                    }
                    for k in linked
                ]
            )
        )
    record_audit(
        session,
        actor,
        "access_policy.project_changed",
        "user",
        person.id,
        project_id=project.id,
        before={k: before[k] for k in linked if k in before},
        after={k: enabled for k in linked},
    )
    await session.commit()
    return await person_project_access(session, user_id, project_id)


async def reset_section(
    session: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    section: str,
) -> PersonProjectAccessOut:
    """Back to the defaults for this person, project and section only."""
    if section not in SECTION_KEYS:
        raise AppError(404, "NOT_FOUND", "Section not found.")
    person = await _person(session, user_id)
    project, _ = await _project_for(session, person, project_id)
    keys = [c.key for c in PROJECT_CONTROLS if c.section == section]
    before = await _saved(session, person, project)
    removed = {k: v for k, v in before.items() if k in keys}
    if removed:
        await session.execute(
            delete(ProjectPermissionSetting).where(
                ProjectPermissionSetting.project_id == project.id,
                ProjectPermissionSetting.user_id == person.id,
                ProjectPermissionSetting.permission.in_(keys),
            )
        )
        record_audit(
            session,
            actor,
            "access_policy.project_reset",
            "user",
            person.id,
            project_id=project.id,
            before={"section": section, **removed},
            after={"section": section},
        )
        await session.commit()
    return await person_project_access(session, user_id, project_id)
