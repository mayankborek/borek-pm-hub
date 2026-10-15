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
├── .github/      PR template and CI workflows
└── docker-compose.yml  (added with the backend setup ticket)
```

## Documentation

- Backend architecture: [docs/architecture/BOREK_PM_HUB_Backend_Architecture.md](docs/architecture/BOREK_PM_HUB_Backend_Architecture.md)

## Running locally

Setup instructions will be added here once the backend skeleton is merged
(target: `docker compose up` starts the API and the database).

## Working on this repository

- `main` is the only long-lived branch. It always contains reviewed, working code.
- Create **one branch per Jira ticket** from `main`, named `<type>/<JIRA-KEY>-<short-description>`:
  - `feature/PMH-4-task-crud-api`
  - `fix/PMH-14-task-filter-bug`
  - `chore/PMH-20-ci-pipeline`
- Include the Jira key in commit messages and the PR title, for example `PMH-4: add task create endpoint`.
- Open a pull request into `main`. CI must pass and another developer must approve.
- Merge with **squash and merge**. The branch is deleted automatically after the merge.
- Never commit secrets or `.env` files. Use `.env.example` for variable names only.

## Environments

| Environment | Purpose | Deployed from |
|---|---|---|
| Local | Development on your machine | Docker Compose |
| Staging | Team testing, demos, acceptance | Every merge to `main` |
| Production | Real use | Release tag with manual approval |
