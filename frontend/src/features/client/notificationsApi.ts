import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import { paths } from '@/app/routes';
import type { ClientNotification } from './types';

type Role = 'client' | 'account_manager' | 'manager' | 'pm';

/** GET /me/notifications: what happened, built into text here from `type` and `params`. */
interface ApiNotification {
  id: string;
  type: string;
  project: { id: string; code: string; name: string } | null;
  entity_type: string;
  entity_id: string;
  params: Record<string, unknown>;
  actor?: { id: string; name: string } | null;
  read_at: string | null;
}
interface ApiNotificationList {
  items: ApiNotification[];
  unread_count: number;
}

const KEY = ['client-notifications'];

function headline(n: ApiNotification, role: Role): string {
  switch (n.type) {
    case 'change_request.review_started':
      return 'Your change request is in review';
    case 'change_request.decided':
      return n.params.decision === 'approved' ? 'Your change request was approved' : 'Your change request was declined';
    case 'change_request.commented':
      return 'New message on your change request';
    case 'change_request.submitted':
      return role === 'client' ? 'A change request was raised for you' : 'A change request was raised';
    case 'status_report.published':
      return 'A progress report is available';
    case 'milestone.shared':
      return 'A milestone was shared with you';
    case 'milestone.moved':
      return 'A milestone date changed';
    case 'milestone.done':
      return 'A milestone was reached';
    case 'requirement.published':
      return 'A requirement is waiting for your answer';
    case 'requirement.answered':
      return 'A requirement was answered';
    case 'milestone.late':
      return 'A milestone is running late';
    case 'task.blocked':
      return `“${String(n.params.title ?? n.params.key ?? 'A task')}” was blocked`;
    case 'task.commented':
      return `${n.actor?.name ?? 'Someone'} commented on “${String(n.params.title ?? n.params.key ?? 'a task')}”`;
    case 'task.mentioned':
      return `${n.actor?.name ?? 'Someone'} mentioned you in “${String(n.params.title ?? n.params.key ?? 'a task')}”`;
    case 'task.assigned':
      return `${n.actor?.name ?? 'Someone'} assigned “${String(n.params.title ?? n.params.key ?? 'a task')}” to you`;
    case 'project.member_added':
      return `You were added to ${String(n.params.name ?? 'a project')}`;
    default:
      return 'You have a new update';
  }
}

/** Where each role's screens live. Account Managers have no change request or requirement tab. */
const SCREENS = {
  client: {
    projects: () => paths.clientProjects,
    project: paths.clientProject,
    milestones: paths.clientMilestones,
    report: paths.clientReport,
    changeRequests: paths.clientChangeRequests,
    requirements: paths.clientProject,
  },
  manager: {
    projects: () => paths.managerProjects,
    project: paths.managerProject,
    milestones: paths.managerMilestones,
    report: paths.managerReport,
    changeRequests: paths.managerChangeRequests,
    requirements: paths.managerProject,
  },
  pm: {
    projects: () => paths.projects,
    project: paths.project,
    milestones: paths.projectMilestones,
    report: paths.projectReport,
    changeRequests: paths.projectChangeRequests,
    requirements: paths.projectChangeRequests,
  },
  account_manager: {
    projects: () => paths.amProjects,
    project: paths.amProject,
    milestones: paths.amMilestones,
    report: paths.amReport,
    changeRequests: paths.amProject,
    requirements: paths.amProject,
  },
};

/** The screen the notification is about; falls back to the project overview. */
function target(n: ApiNotification, role: Role): string {
  const screens = SCREENS[role];
  const project = n.project?.id;
  if (!project) return screens.projects();
  switch (n.entity_type) {
    case 'task':
      return role === 'pm' ? paths.task(n.entity_id) : screens.project(project);
    case 'change_request':
      return screens.changeRequests(project);
    case 'status_report':
      return screens.report(project, n.entity_id);
    case 'milestone':
      return screens.milestones(project);
    case 'requirement':
      return screens.requirements(project);
    default:
      return screens.project(project);
  }
}

function toItem(n: ApiNotification, role: Role): ClientNotification {
  const what = n.params.code ?? n.params.title;
  return {
    id: n.id,
    headline: headline(n, role),
    meta: [n.project?.name, what].filter(Boolean).join(' · '),
    to: target(n, role),
    unread: n.read_at === null,
  };
}

/** The bell's data for a signed-in portal user: newest notifications, unread count and mark-as-read. */
export function useNotificationFeed(role: Role | undefined) {
  const enabled = !!role;
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: KEY,
    enabled,
    queryFn: () => api<ApiNotificationList>('/me/notifications?limit=10'),
    refetchInterval: 60_000,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: KEY });
  const readOne = useMutation({
    mutationFn: (id: string) => api(`/me/notifications/${id}/read`, { method: 'POST' }),
    onSettled: refresh,
  });
  const readAll = useMutation({
    mutationFn: () => api('/me/notifications/read-all', { method: 'POST' }),
    onSettled: refresh,
  });
  return {
    items: role ? (list.data?.items.map((n) => toItem(n, role)) ?? []) : [],
    unread: list.data?.unread_count ?? 0,
    markRead: (id: string) => readOne.mutate(id),
    markAllRead: () => readAll.mutate(),
  };
}
