import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, getApiUser } from '@/shared/api/client';
import { env } from '@/shared/config/env';
import { qs } from '@/features/projects/projectsApi';
import type { Page } from '@/features/projects/types';

/** Mirrors backend EstimateUnit (app/common/enums.py). */
export const ESTIMATE_UNITS = ['minutes', 'hours', 'weeks'] as const;
export type EstimateUnit = (typeof ESTIMATE_UNITS)[number];
export type StatusCategory = 'backlog' | 'todo' | 'in_progress' | 'blocked' | 'done';
export type TaskPriority = 'highest' | 'high' | 'medium' | 'low' | 'lowest';

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
  project_name: string;
  title: string;
  status: { id: string; name: string; category: StatusCategory };
  priority: TaskPriority;
  labels: string[];
  due_date: string | null;
  estimate_value: number | null;
  estimate_unit: EstimateUnit | null;
  assignee: UserBrief | null;
  blocked_at?: string | null;
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
  /** A single project status; only set from the backlog Filter menu. */
  statusId: string;
  priority: TaskPriority | '';
  assigneeId: string;
}

export const emptyFilter: TaskFilter = { q: '', category: '', statusId: '', priority: '', assigneeId: '' };

export const taskKeys = {
  all: ['tasks'] as const,
  list: (scope: string, f: TaskFilter) => ['tasks', 'list', scope, f] as const,
  project: (projectId: string) => ['tasks', 'project', projectId] as const,
};

const filterParams = (f: TaskFilter) => ({
  q: f.q.trim(),
  category: f.category,
  status_id: f.statusId,
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
  blocked_reason: string | null;
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
  estimate_value: number | null;
  estimate_unit: EstimateUnit | null;
  assignee_id: string | null;
  blocked_reason: string | null;
}>;

export const useTask = (id: string) =>
  useQuery({ queryKey: [...taskKeys.all, 'detail', id], queryFn: () => api<TaskDetail>(`/tasks/${id}`), enabled: !!id });

export const useProjectStatuses = (projectId?: string) =>
  useQuery({
    queryKey: ['projects', 'statuses', projectId],
    queryFn: () => api<TaskStatusOption[]>(`/projects/${projectId}/statuses`),
    enabled: !!projectId,
  });

export interface AssignableUser {
  id: string;
  name: string;
  email: string;
  role: string;
}

/** GET /users (PM only): active developers for the assignee pickers, searchable by name or email. */
export const useAssignableUsers = (search: string, enabled = true) =>
  useQuery({
    queryKey: ['users', 'assignable', search.trim()],
    queryFn: () => api<Page<AssignableUser>>(`/users${qs({ role: 'developer', q: search.trim(), page_size: 200 })}`),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

export const useProjectMembers = (projectId?: string) =>
  useQuery({
    queryKey: ['projects', 'members', projectId],
    queryFn: () => api<ProjectMember[]>(`/projects/${projectId}/members`),
    enabled: !!projectId,
  });

/**
 * PATCH /tasks/{id}. The version is read from the cache at send time, so back-to-back edits use the last
 * accepted version. A response is written to the cache only if it is newer than what is already there;
 * "saved" feedback therefore always reflects data the server accepted.
 */
export const useUpdateTask = (task?: TaskDetail) => {
  const qc = useQueryClient();
  const detailKey = [...taskKeys.all, 'detail', task?.id] as const;
  return useMutation({
    mutationFn: (patch: TaskPatch) => {
      const current = qc.getQueryData<TaskDetail>(detailKey) ?? task!;
      return api<TaskDetail>(`/tasks/${current.id}`, { method: 'PATCH', body: JSON.stringify({ ...patch, version: current.version }) });
    },
    onSuccess: (saved) => {
      const cached = qc.getQueryData<TaskDetail>(detailKey);
      if (!cached || saved.version >= cached.version) qc.setQueryData(detailKey, saved);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['projects', 'members'] }); // assigning adds the person to the project
      return qc.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
};

/** Moves a board card to another status (PATCH status_id with the card's version); a blocked status needs a reason. */
export const useMoveTask = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ task, statusId, reason }: { task: Task; statusId: string; reason?: string }) =>
      api<TaskDetail>(`/tasks/${task.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status_id: statusId, version: task.version, ...(reason ? { blocked_reason: reason } : {}) }),
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: taskKeys.all }),
  });
};

export interface TaskInput {
  title: string;
  status_id?: string;
  priority?: TaskPriority;
  due_date?: string | null;
  assignee_id: string | null;
}

/** POST /projects/{id}/tasks, used by the board's inline quick create and the Add Task page. */
export const useCreateTask = (projectId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: TaskInput) =>
      api<Task>(`/projects/${projectId}/tasks`, { method: 'POST', body: JSON.stringify(input) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['projects', 'members'] }); // a new assignee joins the project
      return qc.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
};

/** DELETE /tasks/{id} (PM only): archives the task and refreshes every task list. */
export const useDeleteTask = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/tasks/${id}`, { method: 'DELETE' }),
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

export interface TaskActivity {
  id: string;
  action: string;
  actor: UserBrief;
  changes: Record<string, [unknown, unknown]>;
  created_at: string;
}

/** GET /tasks/{id}/activity: who changed what, newest first. */
export const useActivity = (taskId: string) =>
  useQuery({
    queryKey: [...taskKeys.all, 'activity', taskId],
    queryFn: () => api<Page<TaskActivity>>(`/tasks/${taskId}/activity`),
    enabled: !!taskId,
  });

export interface TaskComment {
  id: string;
  task_id: string;
  author: UserBrief;
  body: string;
  created_at: string;
  edited_at: string | null;
}

const commentsKey = (taskId: string) => [...taskKeys.all, 'comments', taskId] as const;

export const useComments = (taskId: string) =>
  useQuery({ queryKey: commentsKey(taskId), queryFn: () => api<TaskComment[]>(`/tasks/${taskId}/comments`), enabled: !!taskId });

/** POST /tasks/{id}/comments */
export const useAddComment = (taskId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => api<TaskComment>(`/tasks/${taskId}/comments`, { method: 'POST', body: JSON.stringify({ body }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: commentsKey(taskId) }),
  });
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
