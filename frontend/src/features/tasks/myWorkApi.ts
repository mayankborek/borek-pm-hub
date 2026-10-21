import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import { qs } from '@/features/projects/projectsApi';
import type { TaskSummary } from '@/features/projects/types';
import type { Task, TaskPage } from './tasksApi';

export interface AttentionList {
  total: number;
  items: Task[];
}

/** Mirrors backend ProjectCard (app/dashboard/schemas.py). */
export interface ProjectCard {
  id: string;
  code: string;
  name: string;
  status: string;
  tasks: TaskSummary;
}

/** Mirrors backend MyDashboard: the signed-in developer's counts, projects and attention lists. */
export interface MyDashboard {
  summary: TaskSummary;
  projects: ProjectCard[];
  blocked: AttentionList;
  overdue: AttentionList;
}

/** GET /dashboard/me */
export const useMyDashboard = () =>
  useQuery({ queryKey: ['tasks', 'my-dashboard'], queryFn: () => api<MyDashboard>('/dashboard/me?limit=10'), staleTime: 30_000 });

/** GET /me/tasks: everything assigned to me, soonest due first. 200 is the server's page-size cap. */
export const useMyTasks = () =>
  useQuery({
    queryKey: ['tasks', 'mine'],
    queryFn: () => api<TaskPage>(`/me/tasks${qs({ sort: 'due_date', page_size: 200 })}`),
    staleTime: 30_000,
  });
