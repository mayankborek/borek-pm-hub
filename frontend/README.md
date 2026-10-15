# Borek Flow – Frontend

React + TypeScript + Vite. Run: `npm install && npm run dev` (http://localhost:3000, `/api` proxied to :8000).

## Structure

```
src/
├── app/        App shell wiring: providers, router, route guards, routes.ts (URLs + sidebar nav)
├── layouts/    AppLayout (sidebar + topbar)
├── features/   One folder per domain: auth, dashboard, projects, tasks, errors
├── shared/     api client, config, reusable UI, global styles
└── main.tsx
templates/      Static HTML design references (login states). Do not import.
```

## Rules

- Add URLs only in `app/routes.ts`; add nav entries to `navItems` (filtered by role).
- Features never import from other features' internals; share through `shared/`.
- Route guards are UX only; the backend enforces permissions.
- All API calls go through `shared/api/client.ts` (sends `X-Dev-User-Id` in Phase 1).

## Routes

| Path | Access |
|---|---|
| `/login` | Public (redirects if signed in) |
| `/` | Redirects: PM → `/dashboard`, Developer → `/my-work` |
| `/dashboard` | PM |
| `/my-work` | Developer |
| `/projects`, `/projects/:id/{board,list,members}` | Both |
| `/tasks`, `/tasks/:taskId` | Both |

## Stubs to replace

`features/auth/authService.ts` is mocked (`pm@borek.com`, `dev1@borek.com`). Swap for `/auth/dev-users` and `/auth/me` once the backend auth ticket lands.
