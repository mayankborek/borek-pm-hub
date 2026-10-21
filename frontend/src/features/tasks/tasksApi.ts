import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import { qs } from '@/features/projects/projectsApi';

export type StatusCategory = 'backlog' | 'todo' | 'in_progress' | 'blocked' | 'done';
export type TaskPriority = 'critical' | 'high' | 'medium' | 'low';

export interface UserBrief {
  id: string;
  name: string;
  email: string;
}

/** Mirrors backend TaskOut (app/tasks/schemas.py). */
export interface Task {
  id: string;
  key: string;
  project_id: string;
  project_code: string;
  project_name: string;
  title: string;
  status: { id: string; name: string; category: StatusCategory };
  priority: TaskPriority;
  labels: string[];
  due_date: string | null;
  progress: number;
  assignee: UserBrief | null;
  version: number;
}

export interface TaskPage {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
}

export interface TaskFilter {
  q: string;
  category: StatusCategory | '';
  priority: TaskPriority | '';
  assigneeId: string;
}

export const emptyFilter: TaskFilter = { q: '', category: '', priority: '', assigneeId: '' };

export const taskKeys = {
  all: ['tasks'] as const,
  list: (scope: string, f: TaskFilter) => ['tasks', 'list', scope, f] as const,
  project: (projectId: string) => ['tasks', 'project', projectId] as const,
};

const filterParams = (f: TaskFilter) => ({
  q: f.q.trim(),
  category: f.category,
  priority: f.priority,
  assignee_id: f.assigneeId,
});

const PAGE_SIZE = 25;

/** GET /tasks (all projects the user can see), paged with "Load more". `projectId` narrows it to one project. */
export const useAllTasks = (projectId: string, f: TaskFilter) =>
  useInfiniteQuery({
    queryKey: taskKeys.list(projectId || 'all', f),
    queryFn: ({ pageParam }) =>
      api<TaskPage>(
        `/tasks${qs({ ...filterParams(f), project_id: projectId, sort: 'due_date', page: pageParam, page_size: PAGE_SIZE })}`,
      ),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page * last.page_size < last.total ? last.page + 1 : undefined),
    placeholderData: keepPreviousData,
  });

/** GET /projects/{id}/tasks; the project list view shows every task, split into Board and Backlog groups. */
export const useProjectTasks = (projectId: string, f: TaskFilter) =>
  useQuery({
    queryKey: [...taskKeys.project(projectId), f],
    queryFn: () =>
      api<TaskPage>(
        `/projects/${projectId}/tasks${qs({ ...filterParams(f), view: 'list', sort: 'due_date', page_size: 200 })}`,
      ),
    enabled: !!projectId,
    placeholderData: keepPreviousData,
  });

export interface TaskDetail extends Task {
  description: string | null;
  start_date: string | null;
  reporter: UserBrief;
  updated_at: string;
}

export interface TaskStatusOption {
  id: string;
  name: string;
  category: StatusCategory;
}

export interface ProjectMember {
  user_id: string;
  name: string;
  email: string;
}

/** Fields accepted by PATCH /tasks/{id}; `version` is the optimistic-locking counter from the last read. */
export type TaskPatch = Partial<{
  title: string;
  description: string | null;
  status_id: string;
  priority: TaskPriority;
  labels: string[];
  start_date: string | null;
  due_date: string | null;
  assignee_id: string | null;
}>;

export const useTask = (id: string) =>
  useQuery({ queryKey: [...taskKeys.all, 'detail', id], queryFn: () => api<TaskDetail>(`/tasks/${id}`), enabled: !!id });

export const useProjectStatuses = (projectId?: string) =>
  useQuery({
    queryKey: ['projects', 'statuses', projectId],
    queryFn: () => api<TaskStatusOption[]>(`/projects/${projectId}/statuses`),
    enabled: !!projectId,
  });

export const useProjectMembers = (projectId?: string) =>
  useQuery({
    queryKey: ['projects', 'members', projectId],
    queryFn: () => api<ProjectMember[]>(`/projects/${projectId}/members`),
    enabled: !!projectId,
  });

export const useUpdateTask = (task?: TaskDetail) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: TaskPatch) =>
      api<TaskDetail>(`/tasks/${task!.id}`, { method: 'PATCH', body: JSON.stringify({ ...patch, version: task!.version }) }),
    onSettled: () => qc.invalidateQueries({ queryKey: taskKeys.all }),
  });
};
