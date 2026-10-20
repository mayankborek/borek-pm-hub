import { useQuery } from '@tanstack/react-query';
import { qs } from '@/features/projects/projectsApi';
import type { Page, TaskListItem } from '@/features/projects/types';
import { ApiError, api } from '@/shared/api/client';

const isOpen = (t: TaskListItem) => t.status !== 'completed' && t.status !== 'cancelled';

/** A 4xx will not fix itself on retry (403 for non-PMs, 404 while an endpoint is not deployed); only retry network and 5xx failures. */
const retry = (failures: number, err: unknown) => !(err instanceof ApiError && err.status < 500) && failures < 2;

const dashboardQuery = { retry, staleTime: 30_000 } as const;

/** GET /tasks: open tasks past their due date, oldest first. Filtered again client-side. */
export const useOverdueTasks = (today: string) =>
  useQuery({
    ...dashboardQuery,
    queryKey: ['tasks', 'overdue', today],
    queryFn: () => api<Page<TaskListItem>>(`/tasks${qs({ due_before: today, sort: 'due_date', page_size: 200 })}`),
    select: (page) => page.items.filter((t) => isOpen(t) && !!t.due_date && t.due_date < today),
  });

/** GET /tasks: open tasks due from `today` through `end` (inclusive), for "Due this week". */
export const useDueSoonTasks = (today: string, end: string) =>
  useQuery({
    ...dashboardQuery,
    queryKey: ['tasks', 'due-soon', today, end],
    queryFn: () => api<Page<TaskListItem>>(`/tasks${qs({ due_before: end, sort: 'due_date', page_size: 200 })}`),
    select: (page) => page.items.filter((t) => isOpen(t) && !!t.due_date && t.due_date >= today && t.due_date <= end),
  });

/** GET /tasks: tasks currently blocked, across the projects the user can access. */
export const useBlockedTasks = () =>
  useQuery({
    ...dashboardQuery,
    queryKey: ['tasks', 'blocked'],
    queryFn: () => api<Page<TaskListItem>>(`/tasks${qs({ status: 'blocked', page_size: 200 })}`),
    select: (page) => page.items.filter((t) => t.status === 'blocked'),
  });
