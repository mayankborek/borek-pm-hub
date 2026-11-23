import type {
  ChangeRequestStatus,
  ClientHealth,
  ClientMilestone,
  ClientPortalData,
  ClientProject,
  ClientReport,
  ClientUpdate,
  MilestoneState,
} from './types';

/** What GET /client/portal and GET /client/projects/{id} return (only the fields the screens use). */
interface ApiMilestone {
  id: string;
  code: string;
  name: string;
  due_date: string;
  state: MilestoneState;
  progress: number | null;
  requested_date: string | null;
  change_request_code: string | null;
}
interface ApiProject {
  id: string;
  code: string;
  name: string;
  category: string | null;
  start_date: string | null;
  due_date: string | null;
  health: ClientHealth | null;
  progress: number | null;
  published_on: string | null;
  published_by: { name: string; role: string } | null;
  latest_update: { text: string; date: string } | null;
  awaiting_input: number;
  project_manager: { name: string } | null;
}
interface ApiUpdate {
  kind: 'report' | 'change_request' | 'milestone';
  title: string;
  project_name: string;
  occurred_at: string;
  report_id: string | null;
  change_request_id: string | null;
  milestone_id: string | null;
  status: ChangeRequestStatus | 'shared' | 'done' | null;
}
interface ApiPortal {
  organisation: { name: string } | null;
  projects: ApiProject[];
  updates: ApiUpdate[];
}
interface ApiDetail {
  contacts: { name: string; role: string; email: string | null; phone: string | null }[];
  reports: {
    id: string;
    title: string;
    report_date: string;
    health: ClientHealth;
    progress: number | null;
    summary: string;
    published_at: string;
  }[];
  milestones: ApiMilestone[];
  change_requests: { code: string; title: string; status: ChangeRequestStatus }[];
}

type Get = <T>(path: string) => Promise<T>;

export const CR_UPDATE: Record<string, string> = {
  pending: 'Change request raised',
  in_review: 'Change request moved to In review',
  approved: 'Change request approved',
  declined: 'Change request declined',
};

function updateOf(u: ApiUpdate): ClientUpdate {
  let title: string;
  if (u.kind === 'report') title = 'New report shared';
  else if (u.kind === 'milestone') title = u.status === 'done' ? 'Milestone reached' : 'Milestone schedule published';
  else title = CR_UPDATE[u.status ?? 'pending'] ?? 'Change request updated';
  return {
    id: `${u.kind}-${u.report_id ?? u.change_request_id ?? u.milestone_id}-${u.occurred_at}`,
    title,
    meta: `${u.project_name} · ${u.title}`,
  };
}

function projectOf(p: ApiProject, d: ApiDetail): ClientProject {
  return {
    id: p.id,
    code: p.code,
    name: p.name,
    category: p.category ?? '',
    startDate: p.start_date,
    dueDate: p.due_date,
    clientActions: p.awaiting_input,
    latestUpdate: p.latest_update ? { text: p.latest_update.text, date: p.latest_update.date } : undefined,
    health: p.health,
    progress: p.progress,
    publishedOn: p.published_on,
    publishedBy: p.published_by,
    projectManager: p.project_manager?.name ?? null,
    contacts: d.contacts.map((c) => ({ name: c.name, role: c.role, email: c.email ?? '', phone: c.phone ?? undefined })),
    milestones: d.milestones.map(
      (m): ClientMilestone => ({
        id: m.id,
        code: m.code,
        name: m.name,
        dueDate: m.due_date,
        state: m.state,
        progress: m.progress,
        requestedDate: m.requested_date ?? undefined,
        changeRequestRef: m.change_request_code ?? undefined,
      }),
    ),
    changeRequests: d.change_requests.map((c) => ({ ref: c.code, title: c.title, status: c.status })),
    reports: d.reports.map(
      (r): ClientReport => ({
        id: r.id,
        title: r.title,
        reportDate: r.report_date,
        publishedAt: r.published_at,
        health: r.health,
        summary: r.summary,
        progress: r.progress,
      }),
    ),
  };
}

/** The portal list plus one detail call per project, folded into the shape the screens render. */
export async function fetchClientPortal(get: Get): Promise<ClientPortalData> {
  const portal = await get<ApiPortal>('/client/portal');
  const details = await Promise.all(portal.projects.map((p) => get<ApiDetail>(`/client/projects/${p.id}`)));
  return {
    today: new Date().toISOString().slice(0, 10),
    organisation: portal.organisation?.name ?? '',
    notifications: [],
    updates: portal.updates.map(updateOf),
    projects: portal.projects.map((p, i) => projectOf(p, details[i])),
  };
}
