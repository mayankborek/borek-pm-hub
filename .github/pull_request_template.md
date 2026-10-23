## Jira ticket
<!-- Key of the ticket, e.g. PT-19 -->

## What changed
<!-- Short summary of the change and why -->

## How to test
<!-- Steps or commands a reviewer can run -->

## Branch and commits
- [ ] Branch is named `<type>/PT-<n>-short-description` (feature, fix, chore) and was cut from `dev`
- [ ] Every commit message starts with the key, e.g. `PT-19: add login form`
- [ ] I did not push this work straight to `dev` or `main`

## Backend area (Mayank's)
`backend/` (including its Dockerfile) and `docker-compose.yml` are changed by Mayank only.
- [ ] This PR does not touch them, **or** Mayank agreed to it first (say where: chat, ticket)
- [ ] No new database migration, API field or permission rule without his approval

## Checklist
- [ ] Tests added or updated
- [ ] CI passes (ruff, mypy, pytest for the backend; `npm run typecheck` for the frontend)
- [ ] Database migration included (yes / no)
- [ ] API change documented (OpenAPI is up to date)
- [ ] No secrets or `.env` files committed
