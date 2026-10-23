import { useQuery } from '@tanstack/react-query';
import type { TaskSummary } from '@/features/projects/types';
import type { Task } from '@/features/tasks/tasksApi';
import { ApiError, api } from '@/shared/api/client';

/** A 4xx will not fix itself on retry (403 for non-PMs, 404 while an endpoint is not deployed); only retry network and 5xx failures. */
const retry = (failures: number, err: unknown) => !(err instanceof ApiError && err.status < 500) && failures < 2;

const dashboardQuery = { retry, staleTime: 30_000 } as const;

/** Mirrors backend ProjectCard (app/dashboard/schemas.py). */
export interface DashboardProject {
  id: string;
  code: string;
  name: string;
  status: 'planned' | 'active' | 'on_hold' | 'completed';
  start_date: string | null;
  target_end_date: string | null;
  tasks: TaskSummary;
}

/** The first `limit` tasks that need action; `total` is the full count. */
export interface AttentionList {
  total: number;
  items: Task[];
}

/** Mirrors backend PmDashboard. */
export interface PmDashboard {
  active_projects: number;
  projects_total: number;
  summary: TaskSummary;
  projects: DashboardProject[];
  blocked: AttentionList;
  overdue: AttentionList;
}

/** Mirrors backend MyDashboard. */
export interface MyDashboard {
  summary: TaskSummary;
  projects: DashboardProject[];
  blocked: AttentionList;
  overdue: AttentionList;
}

/** GET /dashboard (PM only): summary, project cards, and the blocked and overdue lists. Done tasks are already excluded. */
export const useDashboard = () =>
  useQuery({ ...dashboardQuery, queryKey: ['dashboard'], queryFn: () => api<PmDashboard>('/dashboard') });

/** GET /dashboard/me: the signed-in developer's counts, projects, and attention lists. */
export const useMyDashboard = () =>
  useQuery({ ...dashboardQuery, queryKey: ['dashboard', 'me'], queryFn: () => api<MyDashboard>('/dashboard/me') });
