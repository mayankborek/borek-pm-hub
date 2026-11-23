import { CR_UPDATE } from './portalMapper';
import type {
  ChangeRequestStatus,
  ClientHealth,
  ClientMilestone,
  ClientPortalData,
  ClientProject,
  ClientReport,
  ClientUpdate,
  MilestoneState,
  ProjectTask,
} from './types';

/**
 * Account Managers and Managers cannot call /client/*. They see the same screens built from the staff
 * API they already may read: the project list, published reports, milestones, change requests,
 * stakeholders and requirements. Only the fields the screens use are typed here.
 */
interface ApiProject {
  id: string;
  code: string;
  name: string;
  status: string;
  type: 'internal' | 'external';
  category: string | null;
  start_date: string | null;
  target_end_date: string | null;
  client_organisation: { id: string; name: string } | null;
}
interface ApiMember {
  name: string;
  email: string;
  project_role: 'project_lead' | 'developer';
}
interface ApiReport {
  id: string;
  rag: 'green' | 'amber' | 'red';
  progress_percent: number | null;
  summary: string;
  report_date: string;
  published_at: string | null;
  published_by: { name: string } | null;
}
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
interface ApiChangeRequest {
  code: string;
  title: string;
  status: ChangeRequestStatus;
  created_at: string;
  decided_at: string | null;
  review_started_at: string | null;
}
interface ApiStakeholder {
  id: string;
  version: number;
  name: string;
  role_title: string | null;
  email: string | null;
  phone: string | null;
}
interface ApiTask {
  id: string;
  key: string;
  title: string;
  due_date: string | null;
  status: { name: string; category: string };
}

type Get = <T>(path: string) => Promise<T>;

const HEALTH: Record<ApiReport['rag'], ClientHealth> = { green: 'on_track', amber: 'at_risk', red: 'off_track' };
const PM_ROLE = 'Project Manager';
const MAX_PAGE_SIZE = 200;

/** The same title the client portal gives a status report: "Status report 02.11.2026". */
const reportTitle = (date: string) => `Status report ${date.slice(8, 10)}.${date.slice(5, 7)}.${date.slice(0, 4)}`;

/** A section the role may not read (or that is empty) must not take the whole portal down. */
const softly = async <T>(get: Get, path: string, fallback: T): Promise<T> => {
  try {
    return await get<T>(path);
  } catch {
    return fallback;
  }
};

async function projectOf(get: Get, p: ApiProject, withTasks: boolean) {
  const base = `/projects/${p.id}`;
  const [detail, reports, milestones, crs, stakeholders, requirements, tasks] = await Promise.all([
    softly(get, base, { members: [] as ApiMember[] }),
    softly(get, `${base}/status-reports?state=published&page_size=${MAX_PAGE_SIZE}`, { items: [] as ApiReport[] }),
    softly(get, `${base}/milestones`, [] as ApiMilestone[]),
    softly(get, `${base}/change-requests`, { items: [] as ApiChangeRequest[] }),
    softly(get, `${base}/stakeholders`, [] as ApiStakeholder[]),
    softly(get, `${base}/requirements`, { counts: {} as Record<string, number> }),
    withTasks ? softly(get, `${base}/tasks?page_size=${MAX_PAGE_SIZE}`, { items: [] as ApiTask[] }) : Promise.resolve({ items: [] as ApiTask[] }),
  ]);

  const published = reports.items
    .filter((r) => r.published_at)
    .sort((a, b) => b.published_at!.localeCompare(a.published_at!));
  const newest = published[0];
  const withProgress = published.find((r) => r.progress_percent !== null);
  const leads = detail.members.filter((m) => m.project_role === 'project_lead');

  const project: ClientProject = {
    id: p.id,
    code: p.code,
    name: p.name,
    category: p.category ?? '',
    organisation: p.client_organisation?.name,
    startDate: p.start_date,
    dueDate: p.target_end_date,
    clientActions: requirements.counts.awaiting_acceptance ?? 0,
    latestUpdate: newest ? { text: newest.summary, date: newest.report_date } : undefined,
    health: newest ? HEALTH[newest.rag] : null,
    progress: withProgress?.progress_percent ?? null,
    publishedOn: newest?.published_at?.slice(0, 10) ?? null,
    publishedBy: newest?.published_by ? { name: newest.published_by.name, role: PM_ROLE } : null,
    projectManager: leads[0]?.name ?? null,
    contacts: [
      ...leads.map((m) => ({ name: m.name, role: PM_ROLE, email: m.email })),
      ...stakeholders.map((s) => ({
        name: s.name,
        role: s.role_title ?? 'Stakeholder',
        email: s.email ?? '',
        phone: s.phone ?? undefined,
        stakeholderId: s.id,
        version: s.version,
      })),
    ],
    milestones: milestones.map(
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
    tasks: tasks.items
      .filter((t) => t.due_date && t.status.category !== 'done')
      .map((t): ProjectTask => ({ id: t.id, ref: t.key, title: t.title, status: t.status.name, dueDate: t.due_date! })),
    changeRequests: crs.items.map((c) => ({ ref: c.code, title: c.title, status: c.status })),
    reports: published.map(
      (r): ClientReport => ({
        id: r.id,
        title: reportTitle(r.report_date),
        reportDate: r.report_date,
        publishedAt: r.published_at!,
        health: HEALTH[r.rag],
        summary: r.summary,
        progress: r.progress_percent,
      }),
    ),
  };

  const updates: { at: string; update: ClientUpdate }[] = [
    ...published.map((r) => ({
      at: r.published_at!,
      update: { id: `report-${r.id}`, title: 'New report shared', meta: `${p.name} · ${reportTitle(r.report_date)}` },
    })),
    ...crs.items.map((c) => ({
      at: c.decided_at ?? c.review_started_at ?? c.created_at,
      update: { id: `cr-${p.id}-${c.code}-${c.status}`, title: CR_UPDATE[c.status] ?? 'Change request updated', meta: `${p.name} · ${c.code} ${c.title}` },
    })),
  ];
  return { project, updates };
}

/** The portfolio the role may read: external projects with a client, each assembled in parallel. */
export async function fetchStaffPortal(get: Get, role: 'account_manager' | 'manager'): Promise<ClientPortalData> {
  const list = await get<{ items: ApiProject[] }>(`/projects?type=external&page_size=${MAX_PAGE_SIZE}`);
  const external = list.items.filter((p) => p.type === 'external' && p.client_organisation && p.status !== 'cancelled');
  const built = await Promise.all(external.map((p) => projectOf(get, p, role === 'account_manager')));

  const organisations = [...new Set(external.map((p) => p.client_organisation!.name))];
  return {
    today: new Date().toISOString().slice(0, 10),
    // An Account Manager looks after one client; a Manager sees many, so each project names its own.
    organisation: organisations.length === 1 ? organisations[0] : '',
    notifications: [],
    updates: built
      .flatMap((b) => b.updates)
      .sort((a, b) => b.at.localeCompare(a.at))
      .slice(0, 10)
      .map((u) => u.update),
    projects: built.map((b) => b.project),
  };
}
