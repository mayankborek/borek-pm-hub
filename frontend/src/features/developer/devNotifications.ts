import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { paths } from '@/app/routes';
import { api } from '@/shared/api/client';

/** GET /me/notifications for a developer; the text is built here from `type` and `params`. */
interface ApiNotification {
  id: string;
  type: string;
  project: { id: string; code: string; name: string } | null;
  entity_type: string;
  entity_id: string;
  actor: { id: string; name: string } | null;
  params: Record<string, unknown>;
  created_at: string;
  read_at: string | null;
}
interface ApiNotificationList {
  items: ApiNotification[];
  unread_count: number;
}

export interface DevNotification {
  id: string;
  actor: string;
  headline: string;
  meta: string;
  to: string;
  unread: boolean;
}

const KEY = ['dev-notifications'];

const headline = (n: ApiNotification): string => {
  const who = n.actor?.name ?? 'Someone';
  const task = `“${String(n.params.title ?? n.params.key ?? 'a task')}”`;
  switch (n.type) {
    case 'task.assigned':
      return `${who} assigned ${task} to you.`;
    case 'task.unassigned':
      return `${who} unassigned you from ${task}.`;
    case 'task.mentioned':
      return `${who} mentioned you in ${task}.`;
    case 'task.commented':
      return `${who} commented on ${task}.`;
    case 'task.blocked':
      return `${task} was blocked.`;
    case 'task.attachment_added':
      return `${who} attached ${String(n.params.name ?? 'a file')} to ${task}.`;
    case 'task.updated':
      return n.params.status ? `${task} moved to ${String(n.params.status)}.` : `${who} updated ${task}.`;
    case 'project.member_added':
      return `You were added to ${String(n.params.name ?? 'a project')}.`;
    default:
      return 'You have a new update.';
  }
};

/** "10 minutes ago", "1 hour ago". */
export function ago(iso: string, now = Date.now()): string {
  const secs = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  const rtf = new Intl.RelativeTimeFormat(document.documentElement.lang === 'de' ? 'de' : 'en', { numeric: 'always' });
  if (secs < 60) return rtf.format(-Math.max(1, secs), 'second');
  if (secs < 3600) return rtf.format(-Math.floor(secs / 60), 'minute');
  if (secs < 86400) return rtf.format(-Math.floor(secs / 3600), 'hour');
  return rtf.format(-Math.floor(secs / 86400), 'day');
}

const target = (n: ApiNotification) =>
  n.entity_type === 'task' ? paths.task(n.entity_id) : n.project ? paths.project(n.project.id) : paths.projects;

/** The bell's data: newest notifications, the unread count and mark-as-read. */
export function useDevNotifications() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: KEY, queryFn: () => api<ApiNotificationList>('/me/notifications?limit=10'), refetchInterval: 60_000 });
  const refresh = () => qc.invalidateQueries({ queryKey: KEY });
  const readOne = useMutation({ mutationFn: (id: string) => api(`/me/notifications/${id}/read`, { method: 'POST' }), onSettled: refresh });
  const readAll = useMutation({ mutationFn: () => api('/me/notifications/read-all', { method: 'POST' }), onSettled: refresh });
  const items: DevNotification[] = (list.data?.items ?? []).map((n) => ({
    id: n.id,
    actor: n.actor?.name ?? '',
    headline: headline(n),
    meta: [n.project?.name, ago(n.created_at)].filter(Boolean).join(' · '),
    to: target(n),
    unread: n.read_at === null,
  }));
  return { items, unread: list.data?.unread_count ?? 0, markRead: (id: string) => readOne.mutate(id), markAllRead: () => readAll.mutate() };
}
