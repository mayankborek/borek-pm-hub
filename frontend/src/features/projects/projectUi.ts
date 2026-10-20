import type { Tone } from '@/shared/ui/Pill';
import type { Project, ProjectStatus } from './types';

export const STATUS_LABEL: Record<ProjectStatus, string> = {
  planned: 'Planned',
  active: 'In Progress',
  on_hold: 'On Hold',
  completed: 'Completed',
};

export const STATUS_TONE: Record<ProjectStatus, Tone> = {
  planned: 'neutral',
  active: 'progress',
  on_hold: 'risk',
  completed: 'track',
};

/** "12 Oct 2026", or an em dash when the date is not set. Dates are plain calendar days, so no timezone shift. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** Today as YYYY-MM-DD in the browser's local time. */
export function todayIso(): string {
  const n = new Date();
  const p = (v: number) => String(v).padStart(2, '0');
  return `${n.getFullYear()}-${p(n.getMonth() + 1)}-${p(n.getDate())}`;
}

export const completionOf = (p: Project) => p.task_summary?.completion_percent ?? 0;

/** Today plus `days`, as YYYY-MM-DD in the browser's local time. */
export function addDaysIso(days: number): string {
  const n = new Date();
  n.setDate(n.getDate() + days);
  const p = (v: number) => String(v).padStart(2, '0');
  return `${n.getFullYear()}-${p(n.getMonth() + 1)}-${p(n.getDate())}`;
}

/** Whole calendar days between `due` and `today` (both YYYY-MM-DD); 0 when not overdue or unset. */
export function daysOverdue(due: string | null | undefined, today: string): number {
  if (!due) return 0;
  const ms = (iso: string) => Date.UTC(...(iso.split('-').map(Number) as [number, number, number]).map((v, i) => (i === 1 ? v - 1 : v)) as [number, number, number]);
  return Math.max(0, Math.round((ms(today) - ms(due)) / 86_400_000));
}

export type Health = 'On Track' | 'At Risk' | 'Off Track';

/** The API has no health field yet, so derive it: on hold is off track, blocked or overdue work is at risk. */
export function healthOf(p: Project): Health {
  if (p.status === 'on_hold') return 'Off Track';
  const s = p.task_summary;
  return s && (s.blocked > 0 || s.overdue > 0) ? 'At Risk' : 'On Track';
}
