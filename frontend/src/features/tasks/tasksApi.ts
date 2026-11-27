import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, applyAuth } from '@/shared/api/client';
import { env } from '@/shared/config/env';
import { qs } from '@/features/projects/projectsApi';
import type { Page } from '@/features/projects/types';

/** Mirrors backend EstimateUnit (app/common/enums.py). */
export const ESTIMATE_UNITS = ['minutes', 'hours', 'weeks'] as const;
export type EstimateUnit = (typeof ESTIMATE_UNITS)[number];
export type StatusCategory = 'backlog' | 'todo' | 'in_progress' | 'blocked' | 'done';
export type TaskPriority = 'highest' | 'high' | 'medium' | 'low' | 'lowest';
/** Mirrors backend TaskType (app/common/enums.py). */
export const TASK_TYPES = ['task', 'bug', 'story'] as const;
export type TaskType = (typeof TASK_TYPES)[number];
export const TASK_TYPE_LABEL: Record<TaskType, string> = { task: 'Task', bug: 'Bug', story: 'Story' };

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
  task_type: TaskType;
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
export const useProjectTasks = (projectId: string, f: TaskFilter, scope: TaskScope = {}) =>
  useQuery({
    queryKey: [...taskKeys.project(projectId), f, scope],
    queryFn: () =>
      api<TaskPage>(
        `/projects/${projectId}/tasks${qs({
          ...filterParams(f),
          sprint_id: scope.sprintId,
          backlog: scope.backlog ? 'true' : undefined,
          view: 'list',
          sort: 'due_date',
          page_size: 200,
        })}`,
      ),
    enabled: !!projectId && scope.enabled !== false,
    placeholderData: keepPreviousData,
  });

/** Narrows the project task list by sprint on the server: one sprint's tasks, or the backlog (no sprint / unfinished in a closed one). */
export interface TaskScope {
  sprintId?: string;
  backlog?: boolean;
  enabled?: boolean;
}

/** The project's active sprint id: `undefined` while loading, `null` when none is running. Shares the sprint bar's cache. */
export const useActiveSprintId = (projectId: string) =>
  useQuery({
    queryKey: ['projects', 'sprints', projectId],
    queryFn: () => api<{ items: { id: string; state: 'planned' | 'active' | 'completed' }[] }>(`/projects/${projectId}/sprints`),
    enabled: !!projectId,
    retry: false,
    select: (page) => page.items.find((s) => s.state === 'active')?.id ?? null,
  });

export interface TaskDetail extends Task {
  description: string | null;
  start_date: string | null;
  milestone_id: string | null;
  /** Null = the backlog. */
  sprint_id: string | null;
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
  task_type: TaskType;
  labels: string[];
  start_date: string | null;
  due_date: string | null;
  estimate_value: number | null;
  estimate_unit: EstimateUnit | null;
  assignee_id: string | null;
  blocked_reason: string | null;
  milestone_id: string | null;
  sprint_id: string | null;
}>;

export const useTask =(id: string) =>
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

/** GET /users with no role filter: everyone who can join a project (PMs, Managers, developers, Account Managers). */
export const useMemberCandidates = (search: string, enabled = true) =>
  useQuery({
    queryKey: ['users', 'candidates', search.trim()],
    queryFn: () => api<Page<AssignableUser>>(`/users${qs({ q: search.trim(), page_size: 200 })}`),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

export interface LabelSuggestion {
  name: string;
  task_count: number;
}

/** GET /projects/{id}/labels: labels already used in the project, most used first, optionally narrowed by a search. */
export const useProjectLabels = (projectId: string | undefined, search: string, enabled = true) =>
  useQuery({
    queryKey: ['projects', 'labels', projectId, search.trim()],
    queryFn: () => api<LabelSuggestion[]>(`/projects/${projectId}/labels${qs({ q: search.trim() })}`),
    enabled: enabled && !!projectId,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

export interface SprintOption {
  id: string;
  name: string;
  state: 'planned' | 'active' | 'completed';
}

/** GET /projects/{id}/sprints: active first, then planned, then completed; for the task's Sprint picker. */
export const useProjectSprints = (projectId?: string) =>
  useQuery({
    queryKey: ['projects', 'sprints', projectId, 'options'],
    queryFn: () => api<{ items: SprintOption[] }>(`/projects/${projectId}/sprints${qs({ page_size: 100 })}`),
    enabled: !!projectId,
    select: (page) => page.items,
  });

export interface MilestoneOption {
  id: string;
  code: string;
  name: string;
}

/** GET /projects/{id}/milestones: active milestones by due date; for the task's Milestone picker. */
export const useProjectMilestoneOptions = (projectId?: string) =>
  useQuery({
    queryKey: ['projects', 'milestones', projectId, 'options'],
    queryFn: () => api<MilestoneOption[]>(`/projects/${projectId}/milestones`),
    enabled: !!projectId,
  });

export const useProjectMembers =(projectId?: string) =>
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

/** Changes priority or assignee straight from a board card (PATCH with the card's version). */
export const usePatchTask = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ task, patch }: { task: Task; patch: Pick<TaskPatch, 'priority' | 'assignee_id'> }) =>
      api<TaskDetail>(`/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ ...patch, version: task.version }) }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['projects', 'members'] });
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
  mentions?: UserBrief[];
  created_at: string;
  edited_at: string | null;
}

const commentsKey = (taskId: string) => [...taskKeys.all, 'comments', taskId] as const;

export const useComments = (taskId: string) =>
  useQuery({ queryKey: commentsKey(taskId), queryFn: () => api<TaskComment[]>(`/tasks/${taskId}/comments`), enabled: !!taskId });

export interface CommentInput {
  body: string;
  /** Project members @mentioned in the body (max 20); they get a notification. */
  mention_ids: string[];
}

/** POST /tasks/{id}/comments */
export const useAddComment = (taskId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CommentInput) => api<TaskComment>(`/tasks/${taskId}/comments`, { method: 'POST', body: JSON.stringify(input) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: commentsKey(taskId) }),
  });
};

/** PATCH /tasks/{id}/comments/{commentId}: the author only; `mention_ids` replaces the old mentions. */
export const useEditComment = (taskId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: CommentInput & { id: string }) =>
      api<TaskComment>(`/tasks/${taskId}/comments/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: commentsKey(taskId) }),
  });
};

/** Downloads need the auth header, so fetch the file as a blob and save it. */
export async function downloadAttachment(a: Attachment) {
  const headers = new Headers();
  applyAuth(headers);
  const res = await fetch(`${env.apiBaseUrl}/tasks/${a.task_id}/attachments/${a.id}/download`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const link = Object.assign(document.createElement('a'), { href: url, download: a.name });
  link.click();
  URL.revokeObjectURL(url);
}
