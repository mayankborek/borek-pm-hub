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
