# Borek PM Hub: Backend Architecture Baseline (Phase 1)

> Status: **Draft v0.3** (v0.2 after reading feature specs F01 to F09; v0.3 on 20.10.2026 for the custom-status model and the PT-16 task APIs). Written for the backend developer as the reference point for all Phase 1 work.
> Items marked **[CONFIRM]** are proposals that need a yes/no from the PM or the team lead.
> Source: PDDP v2 (October 2026), the six Phase 1 backend tickets, and the Phase 1 feature specs F01 to F09.

---

## 1. Purpose and scope

Borek PM Hub is an internal, Jira-like project and task management platform for Borek teams.

| | Phase 1 (now) | Later |
|---|---|---|
| Users | Developers and Project Managers (PM) | Clients (portal), admins, viewers |
| Login | **None.** Login button goes to the main page; user picked from seeded accounts | Microsoft Entra ID |
| Core features | Projects, members, tasks (list and Kanban data), assignment, status updates, "My Tasks" | Requirements, milestones, activity, attachments, registers, portfolio, client portal |
| Scale target | ~200 users, **all active at the same time, no degradation** | Same, plus client users |

**This document covers the backend only.** The frontend is a separate codebase that consumes the API.

### Out of scope for Phase 1
Authentication provider, requirements and milestones (pending PM decision), attachments, activity timeline, notifications, registers (risks, issues, decisions), client portal, commercial fields, real-time updates.

---

## 2. Architecture principles

1. **Modular monolith.** One deployable FastAPI service, split into clear modules. No microservices. For ~200 users this is simpler, cheaper and fully sufficient.
2. **API-first.** The frontend talks only to the documented REST API (OpenAPI). The API contract is the product.
3. **Stateless API.** No session state in memory, so we can run N identical copies behind a load balancer. This is the foundation of the "must never break" requirement.
4. **Authentication and authorization are separate.** Who you are (authn) can change from "dev login" to Entra ID without touching what you may do (authz).
5. **Every project-scoped table carries `project_id`.** This makes membership filtering simple now and row-level security possible later.
6. **Add nothing before it is needed.** No Kafka, no Redis, no PostGIS in Phase 1 (see section 4).
7. **Database is the source of truth for integrity.** Constraints, foreign keys and unique indexes enforce rules, not just application code.

---

## 3. System overview

```
                 ┌────────────────────┐
                 │  Frontend (React)  │   separate repo/folder
                 └─────────┬──────────┘
                           │ HTTPS / JSON  (/api/v1/...)
                           ▼
              ┌──────────────────────────┐
              │  Load balancer / Ingress │  (Azure Container Apps ingress)
              └────────────┬─────────────┘
              ┌────────────┴─────────────┐
              ▼                          ▼
     ┌─────────────────┐        ┌─────────────────┐
     │ API replica 1   │  ...   │ API replica N   │   stateless FastAPI
     │ (uvicorn workers)│       │                 │
     └────────┬────────┘        └────────┬────────┘
              └────────────┬─────────────┘
                           │ connection pool
                           ▼
              ┌──────────────────────────┐
              │ PostgreSQL 16            │  single source of truth
              └──────────────────────────┘
```

Inside one API replica:

```
Request → Middleware (request ID, logging, error handling)
        → Router (HTTP only: parse, validate, return)
        → Dependencies (current user, DB session, permission check)
        → Service (business rules, transactions)
        → Repository / SQLAlchemy models (queries)
        → PostgreSQL
```

**Rule:** routers never contain business logic; services never build HTTP responses; only repositories touch the database.

---

## 4. Technology stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Matches PDDP and the team's existing stack |
| Web framework | **FastAPI** | Async, automatic OpenAPI docs, Pydantic integration |
| Validation / schemas | **Pydantic v2** | Separate request/response models per audience (key for the future client portal) |
| ORM | **SQLAlchemy 2.0** (async) + **asyncpg** | Handles many concurrent requests without blocking threads |
| Migrations | **Alembic** | Versioned schema changes |
| Database | **PostgreSQL 16** | Relational data (project, member, task) fits perfectly; supports RLS later |
| Settings | **pydantic-settings** | Typed config from environment variables |
| Server | **Gunicorn + Uvicorn workers** | Production-grade process management |
| Testing | **pytest, pytest-asyncio, httpx** | API tests against a real Postgres |
| Quality | **Ruff** (lint + format), **mypy** | Fast, consistent code quality |
| Packaging | `uv` or `pip` + `requirements.txt` **[CONFIRM team preference]** | |
| Local environment | **Docker Compose** (api + postgres) | One command to run everything |
| Target hosting | **Azure** (Container Apps, Azure Database for PostgreSQL Flexible Server, Key Vault, Application Insights) | Per PDDP, "most probably Azure" |
| Load testing | **k6** or **Locust** | Prove the 200-concurrent-user requirement |

### Deliberately NOT in Phase 1

| Technology | Why not now | When to reconsider |
|---|---|---|
| Kafka | No event streaming need; adds big operational cost | Almost certainly never for this scale |
| Redis | Postgres is fast enough for 200 users; one less moving part | When load tests show a real hotspot, or for real-time fan-out (Phase 3) |
| PostGIS | No geographic data | Never |
| Microservices | Two developers; no independent scaling need | Only if Borek X integration forces a split |
| Background job queue | No async work in Phase 1 | Phase 2 (email/Teams notifications, imports) |

---

## 5. Repository structure

```
borek-pm-hub/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app factory, router registration
│   │   ├── core/                  # Cross-cutting infrastructure
│   │   │   ├── config.py          # Settings from environment
│   │   │   ├── database.py        # Engine, session factory, base model
│   │   │   ├── errors.py          # Custom exceptions + global handlers
│   │   │   ├── logging.py         # Structured logging, request ID
│   │   │   ├── pagination.py      # Shared pagination schema/helpers
│   │   │   └── middleware.py      # Request ID, timing, CORS
│   │   ├── auth/                  # WHO the user is (swappable)
│   │   │   ├── router.py          # /auth/dev-users, /auth/login, /auth/me
│   │   │   ├── security.py        # Argon2 password hashing, JWT access tokens
│   │   │   ├── dependencies.py    # get_current_user()
│   │   │   ├── providers/
│   │   │   │   ├── dev.py         # Phase 1: user picked from seed accounts
│   │   │   │   ├── local.py       # Email + password, bearer token (AUTH_MODE=local)
│   │   │   │   └── entra.py       # Later: Entra ID token validation (stub)
│   │   │   └── permissions.py     # WHAT the user may do: can(user, action, resource)
│   │   ├── users/                 # User model, schemas, service, router
│   │   ├── projects/              # Projects and project memberships
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   ├── service.py
│   │   │   └── router.py
│   │   ├── tasks/                 # Tasks, assignment, status workflow, "my tasks"
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   ├── service.py
│   │   │   ├── statuses.py        # Per-project statuses and the category rules
│   │   │   └── router.py
│   │   ├── health/                # /health (liveness) and /ready (readiness)
│   │   └── common/                # Shared enums, constants, small utilities
│   ├── alembic/                   # Migrations
│   │   └── versions/
│   ├── scripts/
│   │   └── seed.py                # Seed PM, developers, sample projects/tasks
│   ├── tests/
│   │   ├── conftest.py            # Test DB, fixtures, PM/Dev test users
│   │   ├── test_health.py
│   │   ├── test_projects.py
│   │   ├── test_tasks.py
│   │   ├── test_permissions.py    # Role x endpoint x own/foreign project
│   │   └── load/                  # k6 / Locust scripts
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── pyproject.toml / requirements.txt
│   └── .env.example
├── frontend/                      # Owned by the frontend developer
├── docs/
│   ├── architecture/              # This document + diagrams
│   ├── decisions/                 # ADRs: one short file per decision
│   ├── api/                       # Exported OpenAPI spec, Postman collection
│   └── runbook.md                 # How to run, deploy, troubleshoot
├── .github/workflows/  (or azure-pipelines.yml)   # CI [CONFIRM CI platform]
├── docker-compose.yml
└── README.md
```

**Module rule:** a module may import another module's **service**, never its tables or repository directly. This keeps modules separable, which also keeps the later move into Borek X realistic.

---

## 6. Authentication in Phase 1 (no login) and the path to Entra ID

You asked for no authentication in Phase 1: the login button just opens the main page. We still need to know **which user is acting**, otherwise "PM vs Developer", "my tasks" and "only assigned projects" cannot work or be tested. **[CONFIRM]** Proposal:

1. The login screen shows the **seeded users** (e.g. "Test PM", "Dev 1", "Dev 2") returned by `GET /api/v1/auth/dev-users`. The person picks one, and the frontend sends `X-Dev-User-Id: <uuid>` on every request.
2. The backend dependency `get_current_user()` reads that header when `AUTH_MODE=dev`.
3. **Everything after that is real**: role checks, membership checks and ownership checks all run against that user. Ticket 2's "Definition of Done" (PM and Developer accounts, role enforcement, forbidden responses) is fully testable.
4. **Safety rule:** the app **refuses to start** if `AUTH_MODE=dev` and `ENVIRONMENT=production`. Dev mode must never be reachable from outside a trusted network. If staging on Azure is publicly reachable, restrict it (IP allow-list or Azure ingress restriction) until real login exists.
5. Later: add `providers/entra.py` that validates the Entra token and maps it to a `User` row. Routers, services and permission checks do not change. Switch with `AUTH_MODE=entra`.

> Note: F01 (Sprint 01) also describes a sign-in page, logout and expired sessions. Confirm with the PM that these move to the post-Phase-1 login work. The user picker covers "role resolved, correct landing page" (PM to dashboard, Developer to My Work).
>
> This means Ticket 2 changes from "integrate the authentication provider" to "build the identity-and-permissions layer with a dev provider". Tell the PM so the ticket wording matches reality.

### 6.1 Update 22.10.2026: three sign-in modes (`AUTH_MODE`)

| Mode | Use | How |
|---|---|---|
| `dev` | Local development only | `X-Dev-User-Id` header, no password. The app refuses to start with it when `ENVIRONMENT=production`. |
| `local` | Staging, pilot, and people **outside** the Microsoft tenant (later: clients), plus the QA accounts | `POST /auth/login` `{email, password}` returns `{access_token, token_type, expires_in, user}`. The frontend sends `Authorization: Bearer <token>`. Argon2 hashes, HS256 JWT (8 h, `SECRET_KEY` of 32+ characters is required), one generic error for every failure, lockout after repeated failures. |
| `entra` | Staff, later | Microsoft Entra ID. Not built (501). |

Accounts are created by hand with SQL (hash from `python -m scripts.hash_password`); there is no sign-up, email, password-reset flow or admin UI in Phase 1. `python -m scripts.bootstrap_users` creates one QA PM and one QA developer from environment variables (`BOOTSTRAP_*`), and `docker compose up` runs it on every start. Tokens cannot be revoked before they expire, but deactivating a user (`is_active = false`) blocks them at once. A later change can allow `entra` and `local` side by side (try the bearer token issuer, then fall back); routers, services and `can()` do not change. **Scope addition: tell the PM.**

---

## 7. Data model (Phase 1)

### Conventions
- UUID primary keys (`id`), plus human-readable identifiers: project `code` (entered by the PM) and task key (`<project code>-<n>`, e.g. `BFL-27`).
- Every table: `created_at`, `updated_at` (UTC, timestamptz). Mutable business tables also have `version` (integer, for optimistic locking) and `archived_at` (soft delete, nothing is physically deleted).
- Priorities, roles and status categories are stored as **varchar with CHECK constraints** (not native Postgres enums), because adding a value later is then a simple migration. Task statuses are **rows** (`project_statuses`), defined per project.
- All timestamps are stored in UTC; due dates are plain `date`.

### Entities

```
users 1 ──── * project_members * ──── 1 projects
  │                                       │ 1        │ 1
  │ (assignee)                            │          └── * project_statuses
  └──────────────── * tasks * ────────────┘                      │ 1
                      │ 1                └─ (status_id, project_id) ─┘
                      ├── * task_comments      (author_id -> users)
                      ├── * task_attachments   (uploaded_by -> users)
                      └── * task_activity      (actor_id -> users)
```

**users**
| Column | Notes |
|---|---|
| id, name, email (unique) | |
| global_role | `pm` / `developer` (same role names as the feature specs; extensible: `admin`, `client`, `viewer` later) |
| external_id | nullable now; will hold the Entra object ID later |
| password_hash | nullable; Argon2 hash for `AUTH_MODE=local` accounts (people outside the Microsoft tenant, QA accounts). Empty for Entra accounts. Added 22.10.2026 (migration 0004) |
| failed_login_count, locked_until | login lockout: 5 wrong passwords in a row lock the account for 15 minutes (`MAX_FAILED_LOGINS`, `LOCKOUT_MINUTES`) |
| is_active | |

**projects**
| Column | Notes |
|---|---|
| id, code (unique short code, entered by the PM, **cannot change after creation**), name (required), description | F02 |
| status | e.g. `planned`, `active`, `on_hold`, `completed` **[CONFIRM values with PM]** |
| start_date, target_end_date | Rule: target_end_date must not be before start_date |
| created_by (FK users) | |
| task_counter | integer, last used task number; used to generate the task key safely (see below) |

**project_members**
| Column | Notes |
|---|---|
| project_id, user_id (**unique together**) | |
| project_role | `project_lead` / `developer` (extensible) |
| source | `invitation` / `task_assignment` |
| granted_by, granted_at | |

**project_statuses** (added in v0.3: statuses are customizable per project, Jira-style)
| Column | Notes |
|---|---|
| id, project_id (FK) | `(id, project_id)` is unique so tasks can reference both |
| name | 1 to 50 characters, unique per project (case-insensitive check in the service) |
| category | `backlog` / `todo` / `in_progress` / `blocked` / `done`. Dashboards, "overdue" and the blocked rules use the category, so renaming a status is always safe |
| position | order of the board columns |

Every project starts with 7 statuses: Backlog, To do, In progress, Code review, Testing, Blocked, Done. The PM and the project lead can add, rename, reorder and delete statuses; a project always keeps at least one `done` status. Deleting a status that tasks use needs a target status (`move_to`).

**tasks**
| Column | Notes |
|---|---|
| id, project_id (FK, indexed) | |
| key | `<project code>-<n>` (e.g. `BFL-27`), unique per project, never reused |
| title (required), description | |
| status_id | FK to `project_statuses` through the composite key `(status_id, project_id)`: a task cannot use another project's status |
| priority | `critical`, `high`, `medium`, `low` |
| labels | text array, max 10 labels of max 30 characters, no duplicates (case-insensitive) |
| start_date, due_date | nullable; due_date must not be before start_date. `due_date` is also the "estimate" of the designs: the date the task should be completed |
| progress | integer 0 to 100, default 0, stored **independently of status** (F03, F08) |
| assignee_id | nullable FK users (unassigned tasks are allowed, F09) |
| blocked_reason, blocked_at | both set while the status is in the `blocked` category (reason required; checked in the service because the status is in another table) |
| position | integer/rank for Kanban order (add when the board needs it) |
| created_by (the reporter), completed_at | `completed_at` is set while the status is in the `done` category |
| version, archived_at | |

**task_comments** (added in v0.4, F08)
| Column | Notes |
|---|---|
| id, task_id (FK), author_id (FK users) | |
| body | text, 1 to 5000 characters |
| edited_at, archived_at | only the author edits; the author or a PM archives (nothing is deleted) |

**task_attachments** (added in v0.4, F08)
| Column | Notes |
|---|---|
| id, task_id (FK), uploaded_by (FK users) | |
| kind | `file` (stored by the app) or `link` (URL only). CHECK: a link has `url`, a file has `storage_key` |
| name | display name (file name without any path, or the link's name or host) |
| url | links only, http/https, max 2000 characters |
| storage_key, content_type, size_bytes | files only. The file lives in `UPLOAD_DIR` under the random key (a Docker volume); max `MAX_UPLOAD_MB` (10). Moving to Azure Blob Storage later changes only `core/storage.py` |
| archived_at | uploader or PM archives; the stored file is kept |

**task_activity** (added in v0.4, F08; rows are only ever added)
| Column | Notes |
|---|---|
| id, task_id (FK), actor_id (FK users), created_at | |
| action | `created`, `updated`, `archived`, `commented`, `attachment_added`, `attachment_removed` |
| changes | jsonb `{field: [old, new]}` with readable values (status and assignee names, not ids), written in the same transaction as the change |

Indexes: `(task_id, created_at)` on all three tables.

### Reserved for later (no tables now)
`requirement_id` and `milestone_id` on tasks, `status_reports`. Adding a nullable column or a new table is a cheap migration, so we do **not** build them until the PM decides (see section 12).

### Indexes (create from day one)
- `tasks(project_id, status_id)` (board and list)
- `tasks(assignee_id, status_id)` ("my tasks")
- `project_statuses(project_id, position)` (board columns)
- `tasks(project_id, key)` unique
- `project_members(user_id)` and `(project_id, user_id)` unique
- `tasks(project_id, due_date)` and `tasks(project_id, updated_at)` (sort by due date / last updated, F04)

### Rules enforced in the database
- A task's status must belong to the task's project (composite foreign key `(status_id, project_id)`).
- A task's assignee must be a member of the task's project. Enforce in the service **and** double-check with a test (a composite FK or constraint trigger is possible later).
- `project_members` cannot contain the same user twice for a project.
- A project always has at least one `project_lead` (service rule).

### Generating the task key safely under concurrency
Increment `projects.task_counter` in the same transaction that inserts the task, using an atomic `UPDATE projects SET task_counter = task_counter + 1 WHERE id = :id RETURNING task_counter`. The row lock serializes concurrent creators, so there are no duplicates or gaps from races, and numbers are never reused because tasks are archived, not deleted. The key is the project code, a dash and that number (`BFL-27`).

---

## 8. Authorization (permission matrix, Phase 1)

Enforced in one function `can(user, action, resource)`, called from every endpoint through a dependency. **[CONFIRM the whole matrix with the PM; this is the "approved role-permission matrix" Ticket 2 depends on.]**

| Action | Manager (PM) | Developer |
|---|---|---|
| Create / update / archive project | Yes | No |
| List projects | All projects | Only projects they are a member of |
| View project details | Yes | Only if member |
| Add / remove / change project members | Yes | No |
| Create task | Yes | Yes, in projects they are a member of, **assigned to themselves only** |
| Add / rename / reorder / delete statuses | Yes | Only the project lead of that project |
| Edit task details (title, description, priority, due date) | Yes | No |
| Assign / reassign task | Yes, to any active user (non-members are added to the project) | No |
| List users (assignee picker) | Yes | No |
| Change task status, progress, blocked reason | Any status | Only on tasks assigned to them, any status of the project |
| View tasks in a project | Yes | Yes, **all tasks** of projects they are a member of (like Jira) |
| "My tasks" | Own assigned | Own assigned |
| Archive task | Yes | No |
| Dashboard (metrics, blocked and overdue lists) | Yes, all projects | Yes, but only projects they are a member of (own progress plus per-member counts; **not built yet, F06**) |

**Response codes:** `401` = no/unknown user, `403` = known user, not allowed, `404` = used instead of 403 when the user should not even know the project exists (prevents leaking project existence to non-members).

### Status rules (v0.3, replaces the fixed transition table)

Statuses are defined per project (see `project_statuses` in section 7). Moving a task is **free**: any status of the project to any other. There is no transition table. What guards a move is the **category** of the destination status:

| Destination category | Rule |
|---|---|
| `blocked` | `blocked_reason` is required (not blank); `blocked_at` is set |
| `done` | `completed_at` is set |
| anything else | `blocked_reason`, `blocked_at` and `completed_at` are cleared |

The same rules are applied to every task of a status when the PM changes that status's category or deletes it with a `move_to` target. Developers may move only tasks assigned to them; the PM may move any task. **Decided (20.10.2026): no approval step for done statuses.** If one is ever wanted (for example only a reviewer may complete), it becomes a rule on the `done` category, not a new table.

### Validation rules (from F02, F03, F08, F09)
- Project `code` unique; `name` required; `target_end_date` not before `start_date`.
- Task `title` and `project_id` required; `due_date` not before `start_date`; `progress` between 0 and 100.
- Assignee must be an active member of the task's project (or the task stays unassigned).
- Invalid requests are rejected whole: **no partial records are saved** (F01 Sprint Review check).
- Reassigning a task removes it from the previous assignee's "My Work" automatically (it is the same `assignee_id`).

### PM dashboard metrics (F06) **[CONFIRM definitions]**
All counts cover only projects the PM may manage and come from the same task table as every other view.
| Metric | Proposed definition |
|---|---|
| Active projects | projects with status `active` |
| Total tasks | non-archived tasks |
| Completed / In progress / Blocked | count by status **category** (`done` / `in_progress` / `blocked`) |
| Overdue | `due_date` before today and status category not `done` |
| Completion % | completed / total tasks, rounded; 0 if no tasks |
Define "today" in one timezone (e.g. Europe/Berlin) in one place.

---

## 9. API conventions

- Base path: `/api/v1`. Documented automatically at `/docs` (Swagger) and `/openapi.json`.
- JSON in, JSON out. Names in `snake_case`. Dates ISO 8601 (UTC for timestamps).
- Resource names are plural nouns. Use proper verbs: `GET`, `POST`, `PATCH` (partial update), `DELETE` only where it archives.

### Success responses
- Single object: returned directly.
- Lists: `{ "items": [...], "total": 123, "page": 1, "page_size": 50 }`. Default page size 50, **hard maximum 200**.

### Error responses (one shape everywhere)
```json
{
  "error": {
    "code": "TASK_ASSIGNEE_NOT_MEMBER",
    "message": "The selected user is not a member of this project.",
    "details": [{ "field": "assignee_id", "issue": "not_a_member" }]
  },
  "request_id": "b1f6..."
}
```
| HTTP | When |
|---|---|
| 400 / 422 | Validation failure |
| 401 / 403 / 404 | See section 8 |
| 409 | Version conflict (optimistic locking) or duplicate |
| 500 | Unexpected; logged with `request_id`, **no internals leaked** |

### Concurrency safety
Updates (`PATCH`) include the record's current `version`. If another person changed it first, the API returns `409` and the client reloads. This prevents two people silently overwriting each other, which matters with 200 simultaneous users.

### Phase 1 endpoints (mapped to tickets)

| Endpoint | Purpose | Ticket |
|---|---|---|
| `GET /health`, `GET /ready` | Liveness and readiness (DB check) | 1 |
| `GET /api/v1/auth/dev-users` | Seeded users for the login screen (dev mode only) | 2 |
| `POST /api/v1/auth/login` | Email + password sign-in (`AUTH_MODE=local` only, otherwise 404). Added 22.10.2026, no ticket | 2 |
| `GET /api/v1/auth/me` | Current user, role, memberships | 2 |
| `GET /api/v1/users` | PM only. Active users for the assignee picker: `q` (name or email, case-insensitive), `role` (`pm`/`developer`), `page`, `page_size` (max 200); sorted by name. Added 22.10.2026 | 5 |
| `POST /api/v1/projects` | Create project | 3 |
| `GET /api/v1/projects` | List (scoped by role/membership), searchable with `q`, includes task progress summary per project | 3 |
| `GET /api/v1/projects/{id}` | Details | 3 |
| `PATCH /api/v1/projects/{id}` | Update | 3 |
| `GET/POST /api/v1/projects/{id}/members` | List / add members | 3 |
| `PATCH/DELETE /api/v1/projects/{id}/members/{user_id}` | Change role / remove | 3 |
| `POST /api/v1/projects/{id}/tasks` | Create task | 4 |
| `GET /api/v1/projects/{id}/tasks` | List with filters: `status_id` and `category` (repeatable), `priority` (repeatable), `assignee_id`, `unassigned`, `label`, `due_before`, `due_after`, `overdue` (past due, not in a done status), `q` (title or key), `include_archived` (PM); `sort` = `created_at`, `updated_at`, `due_date`, `priority` (prefix `-` for descending); `page`, `page_size`; `view=list\|board` | 4 |
| `GET /api/v1/tasks` | Cross-project task list for the projects the user can access (same filters plus `project_id`; each task carries `project_name`) | 4 |
| `GET /api/v1/projects/{id}/statuses` | List the project's statuses with task counts | 4 |
| `POST /api/v1/projects/{id}/statuses` | Add a status (PM or project lead) | 4 |
| `PATCH /api/v1/projects/{id}/statuses/{status_id}` | Rename or change category | 4 |
| `PUT /api/v1/projects/{id}/statuses/order` | Reorder (send every status id once) | 4 |
| `DELETE /api/v1/projects/{id}/statuses/{status_id}?move_to=` | Delete; `move_to` required when tasks use it | 4 |
| `GET /api/v1/dashboard` | PM only. `active_projects`, `projects_total`, `summary` (total, completed, in_progress, blocked, overdue, completion_percent = completed / non-archived tasks), `projects[]` cards (status, dates, task counts), `blocked` and `overdue` lists (`{total, items}`, `limit` 1-50, default 10). **Built 21.10.2026, no ticket number** | F06 |
| `GET /api/v1/dashboard/me` | Any user: counts of my assigned tasks, my projects with per-member counts, my blocked and overdue tasks | F06, F07 |
| `GET /api/v1/tasks/{id}` | Task detail | 4 |
| `PATCH /api/v1/tasks/{id}` | Edit task (body carries `version`). PM: any field. Developer: only `status_id`, `progress`, `blocked_reason` on own tasks | 4 |
| `DELETE /api/v1/tasks/{id}` | Archive task | 4 |
| `GET /api/v1/tasks/{id}/activity` | History: who changed what and when, newest first (`changes` = `{field: [old, new]}` with readable values); paginated | F08 |
| `GET/POST /api/v1/tasks/{id}/comments` | List / add a comment (project members and PMs) | F08 |
| `PATCH/DELETE /api/v1/tasks/{id}/comments/{cid}` | Edit (author only) / archive (author or PM) | F08 |
| `GET /api/v1/tasks/{id}/attachments` | Files and links of the task | F08 |
| `POST /api/v1/tasks/{id}/attachments` | Upload a file (`multipart/form-data`, field `file`, max `MAX_UPLOAD_MB`, default 10; stored in `UPLOAD_DIR`) | F08 |
| `POST /api/v1/tasks/{id}/attachments/link` | Attach a link `{url, name?}` (http/https only) | F08 |
| `GET /api/v1/tasks/{id}/attachments/{aid}/download` | Download a stored file (same auth as the API; send as attachment) | F08 |
| `DELETE /api/v1/tasks/{id}/attachments/{aid}` | Archive (uploader or PM); the stored file is kept | F08 |
| `PUT /api/v1/tasks/{id}/assignee` | PM only. Body `{version, assignee_id}`; `null` unassigns. Assignee must be an active user (422 `unknown_user`); if they are not a member yet they are **added to the project automatically** (`source=task_assignment`, role `developer`); same assignee is a no-op; 409 on stale version or archived task. Developers cannot self-assign existing tasks | 5 |
| `POST /api/v1/tasks/{id}/status` | **Not built.** Status changes go through `PATCH /tasks/{id}` (`status_id`, `blocked_reason`); free movement, so no transition table | 5 |
| `GET /api/v1/me/tasks` | My Work (F07): the caller's own tasks across their active projects, default sort `due_date`. Same filters as `GET /tasks`; `assignee_id` and `unassigned` are ignored | 5 |

`view=board` returns `{columns: [{status, total, tasks}], total}`: one column per project status in the project's order, so the frontend does not have to group (at most 1000 tasks).

---

## 10. Scale and reliability: "200 users at once must never break"

200 simultaneous users is a modest load for this design. Roughly, even with everyone actively clicking, that is on the order of tens of requests per second, which one well-built Postgres-backed service handles comfortably. We design for **headroom and graceful behavior**, then **prove it with a load test**.

### Design measures
| Concern | Measure |
|---|---|
| Concurrency | Async FastAPI + asyncpg; **minimum 2 replicas** (so one restart or crash is invisible), scale out on CPU/requests |
| Database connections | Pool per worker with a cap. Rule: `replicas x workers x pool_size` must stay **below** Postgres `max_connections` (with margin). Use the managed PgBouncer option on Azure PostgreSQL if needed |
| Slow queries | The indexes in section 7; pagination everywhere (hard max 200/page); **no N+1** (use `selectinload`/joins); no unbounded list endpoints |
| Hot paths | "My tasks", project task list, project list. These get explicit query tests and `EXPLAIN` review |
| Data integrity under races | Atomic task-key generation, optimistic locking, DB constraints |
| Failure isolation | Request timeouts, DB statement timeout, graceful shutdown, readiness check removes a bad replica from rotation |
| Overload protection | Sensible worker limits and request size limits. Rate limiting can be added at ingress if ever needed |
| Observability | Structured JSON logs with `request_id`, Application Insights, alerts on error rate and latency |
| Database safety | Automated backups and point-in-time restore, migrations backward-compatible (expand/contract) so deploys do not break running replicas |

### Targets (aligned with the PDDP)
- Task list or board with 200 tasks: **< 1 s**.
- Single-item operations: **p95 < 300 ms**.
- Availability 99.5% in business hours.

### Proof
A k6/Locust script simulates **200 concurrent users** (mix: 70% reads, 25% task updates, 5% creates) against staging, run as part of Ticket 6. Record p95 latency, error rate and DB connection usage. A "no critical defects" sign-off requires this test to pass. Seed the test database with realistic volume (for example 50 projects, 20,000 tasks) so we test the real situation, not an empty database.

---

## 11. Designing now for later phases (clients, auth, more features)

| Later need | How the baseline already supports it |
|---|---|
| Entra ID login | Auth provider is swappable; `users.external_id` is reserved |
| Client users (Phase 2) | `global_role` and `project_role` are extensible; clients get a **separate router prefix (`/portal/v1`) with separate response schemas**, so internal fields cannot leak by mistake |
| Defense in depth | All project tables have `project_id`, so PostgreSQL row-level security can be added without redesign |
| Requirements and milestones | Added as new tables and nullable FK columns on `tasks`, no rework |
| Activity / audit history | **Built for tasks** (`task_activity`, v0.4). Project-level and member changes are not recorded yet; the same hook pattern in the service layer extends it |
| Notifications | Phase 1: simple polling endpoint. Phase 2: add a Postgres-backed job queue and worker |
| Real-time board | Phase 3, using WebSockets or SSE; the stateless design stays |
| Moving into Borek X | Modules do not touch each other's tables; the API is documented |

---

## 12. Open decisions and questions

### For the PM
1. Do tasks **have to** link to a requirement and a milestone in Phase 1? (The PM is writing a doc on this.) Baseline assumption: **no, optional later.**
2. Confirm the **permission matrix** in section 8 (especially: can developers create tasks? which fields may developers edit on their own tasks?).
3. ~~Status workflow~~ decided 20.10.2026: statuses are per project, tasks move freely, no approval step for done (section 8).
4. Confirm **project status values** and required project fields.
5. Is the "no login in Phase 1" approach in section 6 (pick a seeded user) acceptable, and is the staging environment network-restricted?
6. Is there a sprint concept in Phase 1 (planning/backlog), or just tasks with due dates? Baseline assumption: **no sprints in Phase 1.**

### From the feature specs F01 to F09 (still open there)
- Entra ID, user provisioning, and whether PMs manage user access in the platform (F01).
- Project status options, archive/delete policy, how members are added/removed (F02).
- Is assignment mandatory? Priority labels? Does status automatically change progress? (F03)
- Do developers see all tasks in their projects or only their own, and can they self-assign? (F07)
- Is a blocked reason required, and is drag and drop mandatory? (F05)
- Are comments, attachments, history and requirement/milestone links in Phase 1? (F08)
- Does "Dataset Feature" just mean the data model plus seed data? Baseline assumption: **yes** (F09).

### For the team
7. CI/CD platform: GitHub Actions or Azure DevOps?
8. Azure subscription and who provisions it (staging for Phase 1)?
9. Package/dependency tooling (`uv` vs `pip`)?
10. API contract handoff: should the frontend generate its client from our OpenAPI spec?

---

## 13. Ticket-to-architecture map and suggested order

| Ticket | What it delivers in this architecture |
|---|---|
| **1. Setup, DB, dev environment** | `core/` (config, database, errors, logging), Docker Compose, Alembic baseline, models for users/projects/members/tasks, health endpoints, OpenAPI, seed script, CI skeleton |
| **2. Auth and RBAC** | `auth/` (dev provider, `get_current_user`), `permissions.py`, 401/403/404 behavior, `/auth/me`, permission tests |
| **3. Project APIs** | `projects/` module, membership endpoints |
| **4. Task CRUD** | `tasks/` module, custom statuses (`project_statuses`, `statuses.py`), filters, pagination, board view response |
| **5. Assignment, status, my tasks** | Assignment validation, `/me/tasks` (built), optimistic locking on status changes (the category rules replace `workflow.py`) |
| **6. Integration and testing** | Frontend integration, end-to-end PM→Developer flow, persistence check, **200-user load test**, Sprint Review readiness |

**Not covered by your six tickets:**
- Dashboard metrics API (F06): **will be built** (the team needs it and the UI designs exist), even without a ticket; raise a ticket with the PM so it is planned
- Cross-project task list and keyword search (F04)
- Seed/sample data covering overdue, blocked, unassigned and completed cases for both roles (F09). It fits inside Ticket 1.
- Task activity/comments, if the PM keeps them in Phase 1 (F08)

**Suggested build order inside Ticket 1** (so everything after it moves fast):
1. Repo, Docker Compose, config, health endpoint
2. Database connection, Alembic, base model
3. The four models and the first migration
4. Error handling, response conventions, request ID logging
5. Seed script and `.env.example`
6. README with "run it in 5 minutes", CI running lint and tests

---

## 14. Definition of "architecture done" for Phase 1

- [ ] PM has confirmed items 1 to 6 in section 12 (or assumptions are recorded as ADRs).
- [ ] `docker compose up` starts API and database, migrations applied, seed data loaded.
- [ ] Permission tests cover every role x endpoint x own/foreign project.
- [ ] 200-concurrent-user load test passes on staging.
- [ ] Dev auth cannot start in production.
- [ ] OpenAPI spec exported to `docs/api/` and shared with the frontend developer.

---

## 15. Git workflow, environments and Jira integration

### 15.1 Environments vs. branches
The PDDP defines three **environments**: Local, Staging, Production. Environments are not the same thing as branches. Keep the branch model small (two developers):

| Branch / ref | Purpose | Deploys to |
|---|---|---|
| `dev` | Integration branch for **everyone** (backend, frontend). Always working, always reviewed | **Staging** automatically on every merge |
| `main` | Released code only. Updated by a PR from `dev` at the end of a sprint (release) | **Production**, after manual approval, from a tag |
| tag `v0.1.0`, `v0.2.0`, ... | A release you decided to ship | Production |
| `feature/...`, `fix/...`, `chore/...` | Short-lived work branches, one per Jira ticket, created from `dev` | Nothing (CI runs only) |

> Decision (team): `dev` stays the shared branch; `main` changes only when a sprint is released. Record it in `docs/decisions/`.

### 15.2 One branch per ticket
Yes: **one branch per Jira ticket**, not per feature document and not one long branch for everything. Big tickets (Ticket 1) become several branches and PRs.

```
feature/PT-1-project-skeleton-and-docker
feature/PT-1-database-models-and-migration
feature/PT-2-dev-auth-and-permissions
fix/PT-14-task-filter-wrong-status
chore/PT-20-ci-pipeline
```
Format: `<type>/<JIRA-KEY>-<short-kebab-description>`. (`PT` is the Jira project key) The Jira key is what makes Jira link the branch, commits and PRs to the ticket automatically.

### 15.3 Daily flow
1. Pick the ticket, move it to *In Progress*.
2. `git switch dev && git pull`, then `git switch -c feature/PT-4-task-crud-api`.
3. Commit small and often: `PT-4: add task create endpoint`.
4. Push, open a **Pull Request** into `dev`. PR title starts with the key: `PT-4: Task CRUD APIs`.
5. CI must pass; the **other developer reviews** (this is your PDDP Definition of Done).
6. **Squash and merge** into `dev`, delete the branch, Jira moves to Done.
7. Release (end of sprint): open a PR from `dev` into `main`, merge it with a **merge commit** (not squash), tag `main`, approve the production deployment.

Keep PRs small (roughly under 400 changed lines) so reviews are fast and conflicts rare.

### 15.4 Branch protection on `dev` and `main`
- No direct pushes; changes only via PR.
- At least 1 approval; the author cannot approve their own PR.
- Required checks: lint (Ruff), type check (mypy), tests, and the Alembic check below.
- Require branches to be up to date before merging.
- Merge style: **squash** for ticket PRs into `dev`; **merge commit** for release PRs from `dev` into `main`. Squashing a release makes `dev` and `main` drift apart and causes repeated conflicts.

### 15.5 Alembic gotcha with two developers
If both of you create a migration from the same starting point, Alembic ends up with **two heads** and deploys break. Rules:
- One migration per PR; never edit a migration that is already merged.
- Add a CI step that fails if `alembic heads` returns more than one head.
- If it happens after a merge: rebase your branch, regenerate or re-point `down_revision`, and re-run the tests.

### 15.6 Monorepo
Use **one repo** (`borek-pm-hub`) with `backend/`, `frontend/`, `docs/` as in section 5. For two developers it means one Jira link, one CI setup, and API changes plus frontend changes can ship in one PR when needed.

### 15.7 Setting up the repository (do this first)
1. Create the repo on the company's platform (GitHub or Azure DevOps; this is PDDP open point 1 and decision D-06, so confirm). Private, name `borek-pm-hub`.
2. Make the **first commit directly on `main`**: `README.md`, `.gitignore` (Python, Node, `.env`), `.editorconfig`, `docker-compose.yml` placeholder, `backend/.env.example`, `docs/` with this document.
3. Never commit `.env` or secrets; commit `.env.example` only.
4. Turn on branch protection (15.4) **after** that first commit.
5. Add a PR template (what changed, how to test, Jira key, migration yes/no) and a minimal CI workflow (lint + tests).
6. Add `pre-commit` with Ruff so formatting problems never reach a PR.

### 15.8 Connecting the repo to Jira
1. In Jira, install the Atlassian app for your Git platform (for GitHub: **GitHub for Jira**). This normally needs a **Jira admin**, so ask the PM or IT early.
2. Connect the organisation/account and select the `borek-pm-hub` repo.
3. From then on, any branch name, commit message or PR title containing the key (`PT-4`) shows up on that ticket under **Development** (branches, commits, PRs, build status).
4. Optional Jira automation: PR opened moves the ticket to *In Review*; PR merged moves it to *Done*.
5. Check that the connector exists for your platform if you use Azure DevOps; GitHub, GitLab and Bitbucket have official ones.

### 15.9 Hotfix
If production breaks: branch `fix/PT-xx-...` from the **release tag**, fix, PR into `main`, tag a patch release (`v0.1.1`), deploy, then merge `main` back into `dev` so the fix is not lost. Never patch production by hand.
