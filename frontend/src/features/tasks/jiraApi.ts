import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, applyAuth } from '@/shared/api/client';
import { env } from '@/shared/config/env';
import { taskKeys, type TaskFilter } from './tasksApi';

export type DuplicatePolicy = 'skip' | 'update';

export interface ImportRowError {
  row: number;
  jira_key: string | null;
  field: string | null;
  message: string;
}

/** POST /jira/import/preview: nothing is written; the batch is held server-side until committed or expired. */
export interface ImportPreview {
  batch_id: string;
  file_name: string;
  total_rows: number;
  /** Rows that would be created / matched to an existing task (same Jira key already imported into the project). */
  new_count: number;
  duplicate_count: number;
  invalid_count: number;
  /** Jira values with no match in the project; on commit they follow the options (status → created or first backlog status, user → unassigned). */
  unmapped_statuses: string[];
  unmapped_assignees: string[];
  errors: ImportRowError[];
  sample: { jira_key: string; title: string; status: string; priority: string | null; assignee: string | null }[];
  expires_at: string;
}

export interface ImportCommit {
  on_duplicate: DuplicatePolicy;
  create_missing_statuses: boolean;
}

/** GET /jira/import/{id}: progress and outcome of a committed import. */
export interface ImportJob {
  id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  project_id: string;
  processed: number;
  total: number;
  created: number;
  updated: number;
  skipped: number;
  failed: number;
  errors: ImportRowError[];
}

export const usePreviewImport = () =>
  useMutation({
    mutationFn: ({ projectId, file }: { projectId: string; file: File }) => {
      const body = new FormData();
      body.append('project_id', projectId);
      body.append('file', file);
      return api<ImportPreview>('/jira/import/preview', { method: 'POST', body });
    },
  });

export const useCommitImport = () =>
  useMutation({
    mutationFn: ({ batchId, ...opts }: ImportCommit & { batchId: string }) =>
      api<ImportJob>(`/jira/import/${batchId}/commit`, { method: 'POST', body: JSON.stringify(opts) }),
  });

/** Polls until the job finishes, then refreshes every task list. */
export const useImportJob = (id?: string) => {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ['jira', 'import', id],
    queryFn: async () => {
      const job = await api<ImportJob>(`/jira/import/${id}`);
      if (job.status === 'completed' || job.status === 'failed') void qc.invalidateQueries({ queryKey: taskKeys.all });
      return job;
    },
    enabled: !!id,
    refetchInterval: (q) => (q.state.data?.status === 'completed' || q.state.data?.status === 'failed' ? false : 1500),
  });
};

export type ExportFormat = 'csv' | 'json';

export interface ExportRequest {
  format: ExportFormat;
  /** Explicit selection wins; otherwise the project and filters of the current list are exported. */
  task_ids?: string[];
  project_id?: string;
  filter?: Partial<Record<'q' | 'category' | 'status_id' | 'priority' | 'assignee_id', string>>;
}

export const exportFilter = (f: TaskFilter): ExportRequest['filter'] => ({
  q: f.q.trim(),
  category: f.category,
  status_id: f.statusId,
  priority: f.priority,
  assignee_id: f.assigneeId,
});

/** POST /tasks/export streams a Jira-importable file; fetched as a blob because downloads need the auth header. */
export async function exportTasks(req: ExportRequest) {
  const headers = new Headers({ 'Content-Type': 'application/json' });
  applyAuth(headers);
  const res = await fetch(`${env.apiBaseUrl}/tasks/export`, { method: 'POST', headers, body: JSON.stringify(req) });
  if (!res.ok) throw new ApiError(res.status, res.statusText, await res.json().catch(() => undefined));
  const name = /filename="?([^";]+)"?/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? `tasks.${req.format}`;
  const url = URL.createObjectURL(await res.blob());
  Object.assign(document.createElement('a'), { href: url, download: name }).click();
  URL.revokeObjectURL(url);
}
