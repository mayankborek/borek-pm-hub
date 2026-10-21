import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, getApiUser } from '@/shared/api/client';
import { env } from '@/shared/config/env';
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
  position?: number;
  task_count?: number;
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

export interface TaskInput {
  title: string;
  status_id: string;
  priority: TaskPriority;
  due_date: string | null;
  assignee_id: string | null;
}

/** POST /projects/{id}/tasks, used by the board's inline quick create. */
export const useCreateTask = (projectId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: TaskInput) =>
      api<Task>(`/projects/${projectId}/tasks`, { method: 'POST', body: JSON.stringify(input) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: taskKeys.all }),
  });
};

/** Status management for the Board (PM only): create, rename, reorder, delete. Every change refreshes statuses and tasks. */
export const useStatusActions = (projectId: string) => {
  const qc = useQueryClient();
  const base = `/projects/${projectId}/statuses`;
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['projects', 'statuses', projectId] });
    void qc.invalidateQueries({ queryKey: taskKeys.all });
  };
  const opts = { onSuccess: refresh };
  return {
    create: useMutation({
      mutationFn: (name: string) =>
        api<TaskStatusOption>(base, { method: 'POST', body: JSON.stringify({ name, category: 'todo' }) }),
      ...opts,
    }),
    rename: useMutation({
      mutationFn: (v: { id: string; name: string }) =>
        api<TaskStatusOption>(`${base}/${v.id}`, { method: 'PATCH', body: JSON.stringify({ name: v.name }) }),
      ...opts,
    }),
    reorder: useMutation({
      mutationFn: (ids: string[]) => api<TaskStatusOption[]>(`${base}/order`, { method: 'PUT', body: JSON.stringify({ status_ids: ids }) }),
      ...opts,
    }),
    remove: useMutation({
      mutationFn: (v: { id: string; moveTo?: string }) =>
        api<void>(`${base}/${v.id}${v.moveTo ? `?move_to=${v.moveTo}` : ''}`, { method: 'DELETE' }),
      ...opts,
    }),
  };
};

/** Mirrors backend AttachmentOut (app/tasks/details_schemas.py). */
export interface Attachment {
  id: string;
  task_id: string;
  kind: 'file' | 'link';
  name: string;
  url: string | null;
  download_url: string | null;
  content_type: string | null;
  size_bytes: number | null;
  uploaded_by: UserBrief;
  created_at: string;
}

const attachmentsKey = (taskId: string) => [...taskKeys.all, 'attachments', taskId] as const;

export const useAttachments = (taskId: string) =>
  useQuery({ queryKey: attachmentsKey(taskId), queryFn: () => api<Attachment[]>(`/tasks/${taskId}/attachments`), enabled: !!taskId });

/** POST /tasks/{id}/attachments (multipart, one request per file) and DELETE to archive. */
export const useAttachmentActions = (taskId: string) => {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: attachmentsKey(taskId) });
  return {
    upload: useMutation({
      mutationFn: async (files: File[]) => {
        for (const file of files) {
          const body = new FormData();
          body.append('file', file);
          await api<Attachment>(`/tasks/${taskId}/attachments`, { method: 'POST', body });
        }
      },
      onSettled: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api<void>(`/tasks/${taskId}/attachments/${id}`, { method: 'DELETE' }),
      onSettled: refresh,
    }),
  };
};

/** Downloads need the auth header, so fetch the file as a blob and save it. */
export async function downloadAttachment(a: Attachment) {
  const headers = new Headers();
  const id = getApiUser();
  if (id) headers.set('X-Dev-User-Id', id);
  const res = await fetch(`${env.apiBaseUrl}/tasks/${a.task_id}/attachments/${a.id}/download`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const link = Object.assign(document.createElement('a'), { href: url, download: a.name });
  link.click();
  URL.revokeObjectURL(url);
}
