import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '@/shared/api/client';
import type { Page, Project, ProjectInput } from './types';

export const qs = (params: Record<string, string | number | undefined>) => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : '';
};

export const projectKeys = {
  all: ['projects'] as const,
  list: (q: string) => ['projects', 'list', q] as const,
  detail: (id: string) => ['projects', 'detail', id] as const,
};

/** GET /projects, scoped by the backend to what the user may see. 200 is the server's hard page-size cap. */
export const useProjects = (q = '') =>
  useQuery({
    queryKey: projectKeys.list(q),
    queryFn: () => api<Page<Project>>(`/projects${qs({ q: q.trim(), page_size: 200 })}`),
    placeholderData: keepPreviousData,
  });

export const useProject = (id: string) =>
  useQuery({
    queryKey: projectKeys.detail(id),
    queryFn: () => api<Project>(`/projects/${id}`),
    enabled: !!id,
  });

export const useCreateProject = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ProjectInput) => api<Project>('/projects', { method: 'POST', body: JSON.stringify(input) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
};

/** `code` is immutable after creation, so it is not sent. */
export const useUpdateProject = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ input, version }: { input: Omit<ProjectInput, 'code'>; version: number }) =>
      api<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify({ ...input, version }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
};

export interface FieldErrors {
  [field: string]: string;
}

/** Maps the backend error shape ({ error: { message, details: [{ field, issue }] } }) to form errors. */
export function parseApiError(err: unknown): { message: string; fields: FieldErrors } {
  if (err instanceof ApiError) {
    const e = (err.body as { error?: { message?: string; details?: { field?: string; issue?: string }[] } } | undefined)?.error;
    const fields: FieldErrors = {};
    for (const d of e?.details ?? []) if (d.field) fields[d.field] = d.issue ?? 'Invalid value';
    if (err.status === 403) return { message: 'You do not have permission to do this.', fields };
    if (err.status === 409) return { message: e?.message ?? 'This project was changed by someone else. Reload and try again.', fields };
    return { message: e?.message ?? `Request failed (${err.status}).`, fields };
  }
  return { message: 'Could not reach the server. Check your connection and try again.', fields: {} };
}
