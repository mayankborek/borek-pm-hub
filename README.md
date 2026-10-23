# Borek PM Hub

Internal project and task management platform for Borek teams (Jira-like).
Phase 1 focuses on projects, tasks, assignment and status tracking for Project Managers and Developers.

## Repository structure

```
borek-pm-hub/
├── backend/      FastAPI service, database models, migrations, tests
├── frontend/     Web application
├── docs/
│   ├── architecture/   Architecture documents
│   ├── decisions/      Short decision records (one file per decision)
│   └── api/            Exported OpenAPI spec
├── .github/      PR template, CI (ci.yml) and repo rules (repo-rules.yml)
├── docker-compose.yml       Local environment (API + database)
├── docker-compose.prod.yml  Production-style stack (see below)
└── deploy.env.example       Variable names for .env.prod (copy, fill in, never commit)
```

## Documentation

- Backend architecture: [docs/architecture/BOREK_PM_HUB_Backend_Architecture.md](docs/architecture/BOREK_PM_HUB_Backend_Architecture.md)
- Backend setup and checks: [backend/README.md](backend/README.md)

## Working on this repository

- **`dev`** is the shared integration branch for everyone. All work is merged into `dev`.
- **`main`** contains released code only. It is updated by a pull request from `dev` at the end of a sprint.
- Create **one branch per Jira ticket** from `dev`, named `<type>/<JIRA-KEY>-<short-description>`:
  - `feature/PT-13-project-skeleton`
  - `fix/PT-30-task-filter-bug`
  - `chore/PT-31-ci-pipeline`
- Include the Jira key in commit messages and the PR title, for example `PT-13: add backend skeleton`.
- Open a pull request into `dev`. CI must pass and another developer must approve.
- Two checks run on every push to `dev`/`main` and every pull request (`.github/workflows/repo-rules.yml`): **every commit message starts with `PT-<n>:`**, and **only the backend owner changes `backend/` (including its Dockerfile) and `docker-compose.yml`**. Anyone else asks first; a violation shows as a red check. Merge commits are exempt from the message check.
- `CI` (`.github/workflows/ci.yml`) runs ruff, ruff format, mypy and pytest for the backend (against a throwaway PostgreSQL container, no shared database) and the typecheck for the frontend.
- Merge ticket PRs with **squash and merge**. The branch is deleted automatically afterwards.
- Merge release PRs (`dev` into `main`) with a **merge commit**, not squash.
- Never commit secrets or `.env` files. Use `.env.example` for variable names only.

## Environments

| Environment | Purpose | Deployed from |
|---|---|---|
| Local | Development on your machine | Docker Compose |
| Staging | Team testing, demos, acceptance | Every merge to `dev` |
| Production | Real use | Release tag on `main`, with manual approval |

### Running the production-style stack (one Docker host)

```bash
cp deploy.env.example .env.prod        # fill in every value; .env.prod is git-ignored
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
curl http://localhost:8000/ready
```

The API runs with `ENVIRONMENT=production` and `AUTH_MODE=local` (email + password; the dev user
picker is refused in production). On start it applies migrations, loads the demo data once (only
into an empty database) and creates the QA accounts. The demo users `pm@`, `dev1@`, `dev2@`,
`dev3@borek.test` sign in with `SEED_USER_PASSWORD`. **Before real go-live** remove the demo data and
these accounts, and replace local login with Entra ID. The frontend is not part of this compose
file: serve it separately and put its address in `CORS_ORIGINS`.
