import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, applyAuth } from '@/shared/api/client';
import { env } from '@/shared/config/env';
import { qs } from '@/features/projects/projectsApi';
import { taskKeys, type TaskFilter } from './tasksApi';

export interface ImportIssue {
  row: number;
  external_key: string | null;
  field: string | null;
  message: string;
}

/** Mirrors backend ImportResultOut (app/tasks/schemas.py); `dry_run` results save nothing. */
export interface ImportResult {
  dry_run: boolean;
  total_rows: number;
  created: number;
  skipped_existing: number;
  failed: number;
  failures: ImportIssue[];
  warnings: ImportIssue[];
  warning_count: number;
  unknown_statuses: Record<string, string>;
  unknown_assignees: string[];
  members_added: string[];
  ignored_columns: string[];
  other_projects_in_file: string[];
}

/** POST /projects/{id}/tasks/import?dry_run=…: the same file is sent once to check it and once to save it. */
export const useImportTasks = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, file, dryRun }: { projectId: string; file: File; dryRun: boolean }) => {
      const body = new FormData();
      body.append('file', file);
      return api<ImportResult>(`/projects/${projectId}/tasks/import${qs({ dry_run: String(dryRun) })}`, { method: 'POST', body });
    },
    onSuccess: (result) => {
      if (!result.dry_run) {
        void qc.invalidateQueries({ queryKey: ['projects', 'members'] });
        return qc.invalidateQueries({ queryKey: taskKeys.all });
      }
    },
  });
};

export interface ExportRequest {
  /** Narrows the export to one project (GET /projects/{id}/tasks/export); otherwise everything the user can see. */
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

/** GET /tasks/export (or the project's) streams a CSV; fetched as a blob because downloads need the auth header. */
export async function exportTasks(req: ExportRequest) {
  const headers = new Headers();
  applyAuth(headers);
  const path = req.project_id ? `/projects/${req.project_id}/tasks/export` : '/tasks/export';
  const res = await fetch(`${env.apiBaseUrl}${path}${qs({ ...req.filter })}`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText, await res.json().catch(() => undefined));
  const name = /filename="?([^";]+)"?/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? 'tasks.csv';
  const url = URL.createObjectURL(await res.blob());
  Object.assign(document.createElement('a'), { href: url, download: name }).click();
  URL.revokeObjectURL(url);
}
