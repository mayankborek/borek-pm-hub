import type { WorkItem, WorkPriority } from '@/features/client/types';

/** Status colours from the design: text colour of a status name. */
export const STATUS_COLOR: Record<string, string> = {
  Done: '#17735E',
  'To do': '#5C6178',
  'In progress': '#175DBA',
  'Code review': '#6B3FB8',
  Testing: '#9A5B00',
  Blocked: '#AD1F1F',
};
export const statusColor = (name: string) => STATUS_COLOR[name] ?? '#5C6178';

export const PRIORITIES: WorkPriority[] = ['highest', 'high', 'medium', 'low', 'lowest'];
export const PRIORITY_LABEL: Record<WorkPriority, string> = {
  highest: 'Highest',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  lowest: 'Lowest',
};
export const PRIORITY_COLOR: Record<WorkPriority, string> = {
  highest: '#C94734',
  high: '#C94734',
  medium: '#D88000',
  low: '#2E61D6',
  lowest: '#2E61D6',
};
/** Chevron path per priority (up = high, bars = medium, down = low). */
const PATH: Record<WorkPriority, string> = {
  highest: 'M3 8l4-4 4 4M3 12l4-4 4 4',
  high: 'M3 9l4-4 4 4',
  medium: 'M3 5h8M3 9h8',
  low: 'M3 5l4 4 4-4',
  lowest: 'M3 2l4 4 4-4M3 7l4 4 4-4',
};
export const priorityPath = (p: WorkPriority) => PATH[p];

const STATUS_ORDER = ['To do', 'In progress', 'Code review', 'Blocked', 'Testing', 'Done'];
export const statusRank = (name: string) => {
  const i = STATUS_ORDER.indexOf(name);
  return i < 0 ? STATUS_ORDER.length - 1 : i;
};

/** Distinct status names of the given tasks, in workflow order. */
export const statusNames = (items: WorkItem[]) =>
  [...new Set(items.map((i) => i.status))].sort((a, b) => statusRank(a) - statusRank(b) || a.localeCompare(b));

export const initialsOf = (name: string) =>
  name.split(' ').map((p) => p.charAt(0)).join('').slice(0, 2).toUpperCase();

/** A stable colour per person so the same name always gets the same avatar. */
const AVATARS = ['#D9D2F3', '#CDEBDD', '#FFF1D0', '#DCE8FA', '#F9DCD6'];
export const avatarColor = (name: string) => AVATARS[[...name].reduce((n, c) => n + c.charCodeAt(0), 0) % AVATARS.length];
