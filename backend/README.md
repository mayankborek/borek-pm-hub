# Backend

FastAPI service for Borek PM Hub. Python **3.12** (same version as the Docker image and CI).

## How the backend fits together

Read this first if you change anything in `backend/`. Rules that hold everywhere:

- Routers check **permissions** (through `can()`), services check **data and business rules** and talk to the database.
- The server enforces every permission. Hiding a button in the UI is not security.
- Nothing is physically deleted; rows get `archived_at`.
- Every error has the same shape: `{"error": {"code", "message", "details"}, "request_id": "..."}`.

Polished standalone versions (open in a browser after cloning; GitHub only shows their source):
[architecture](../docs/diagrams/architecture.html), [database schema](../docs/diagrams/database-schema.html), [data flow](../docs/diagrams/data-flow.html).

### Architecture

```mermaid
flowchart LR
    FE["Frontend<br/>/api/v1"] -- "HTTP, JSON" --> MW

    subgraph API ["Backend API (FastAPI)"]
        MW["Middleware<br/>request ID, CORS"] --> RT["Routers<br/>auth, projects"]
        RT -- "who?" --> AU["Auth provider<br/>X-Dev-User-Id"]
        RT -- "may?" --> CAN["can()<br/>single rule book"]
        RT --> SV["Service layer<br/>business rules"]
    end

    ENTRA["Entra ID<br/>later, 501 stub"] -.-> AU
    SV -- "SQL" --> PG[("PostgreSQL 16<br/>constraints")]

    style CAN fill:#f6e3dc,stroke:#bf4520
    style ENTRA stroke-dasharray: 4 3
```

| Folder | Role |
|---|---|
| `app/main.py`, `app/api.py` | Create the app; mount routers under `/api/v1` |
| `app/auth/` | `dependencies.py` (current user), `providers/dev.py` (Phase 1 login), `providers/entra.py` (stub), `permissions.py` (`can()`) |
| `app/projects/` | `router.py` (HTTP + permission checks), `service.py` (rules), `models.py`, `schemas.py` |
| `app/tasks/`, `app/users/` | Models (task endpoints are not built yet) |
| `app/core/` | Config, async DB session, errors, logging, request-ID middleware |
| `alembic/`, `scripts/seed.py`, `tests/` | Migrations, demo data, pytest |

### Database schema

Four tables, integrity enforced by the database. All foreign keys use PostgreSQL's default `ON DELETE NO ACTION`.
Subsystem view: `created_by` / `granted_by` foreign keys, dates and other columns are omitted. Full DDL: `alembic/versions/0001_initial_schema.py`.

```mermaid
erDiagram
    users ||--o{ project_members : "user_id"
    projects ||--o{ project_members : "project_id"
    projects ||--o{ tasks : "project_id"
    users |o--o{ tasks : "assignee_id"

    users {
        uuid id PK
        varchar_200 name
        varchar_320 email UK
        varchar_20 global_role "pm or developer"
        varchar_128 external_id UK "Entra ID, later"
        boolean is_active
    }
    projects {
        uuid id PK
        varchar_20 code UK "immutable"
        varchar_200 name
        varchar_20 status
        integer task_counter "last TSK number"
        integer version "optimistic lock"
        timestamptz archived_at "soft delete"
    }
    project_members {
        uuid id PK
        uuid project_id FK
        uuid user_id FK
        varchar_20 project_role "project_lead or developer"
        varchar_20 source
    }
    tasks {
        uuid id PK
        uuid project_id FK
        varchar_20 key "TSK-### per project"
        varchar_300 title
        varchar_20 status
        uuid assignee_id FK "nullable"
        integer version "optimistic lock"
    }
```

Key constraints: unique `projects.code`, unique `(project_id, user_id)` per membership, unique `(project_id, key)` per task, `progress` between 0 and 100, a `blocked` task needs a reason.
A `version` column on projects and tasks gives optimistic locking: a stale update gets `409`.

### Data flow of one request

Same path for every endpoint (the example is any call that reads or writes a project).

```mermaid
sequenceDiagram
    autonumber
    actor U as PM or Developer
    participant F as Frontend
    participant A as Backend API
    participant D as PostgreSQL

    U->>F: pick a user (dev picker)
    F->>A: request + X-Dev-User-Id header
    Note over A: middleware adds X-Request-ID
    A->>D: authenticate: load user (active?)
    D-->>A: user
    A->>D: load membership facts
    D-->>A: member? assignee?
    Note over A: can(user, action, resource)<br/>deny gives 403, or 404 for non-members
    A->>D: service does the work (constraints, version check)
    D-->>A: rows
    A-->>F: JSON, or the one error shape
    F-->>U: list, form or error
```

## Run locally with a virtual environment (Windows, Command Prompt)

```
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs and http://localhost:8000/health.

## Run everything with Docker (API + database)

From the repository root:

```
copy backend\.env.example backend\.env
docker compose up --build
```

## Checks (the same ones CI runs)

```
ruff check .
ruff format --check .
mypy app
pytest
```

Fix formatting automatically with `ruff check . --fix` and `ruff format .`.

## Dependencies

Versions are pinned in `requirements.txt` (runtime) and `requirements-dev.txt` (tools).
Change a version in the file, rebuild the Docker image and reinstall in the venv together.
