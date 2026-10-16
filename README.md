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
└── docker-compose.yml  Local environment (API + database)
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
- Merge ticket PRs with **squash and merge**. The branch is deleted automatically afterwards.
- Merge release PRs (`dev` into `main`) with a **merge commit**, not squash.
- Never commit secrets or `.env` files. Use `.env.example` for variable names only.

## Environments

| Environment | Purpose | Deployed from |
|---|---|---|
| Local | Development on your machine | Docker Compose |
| Staging | Team testing, demos, acceptance | Every merge to `dev` |
| Production | Real use | Release tag on `main`, with manual approval |
