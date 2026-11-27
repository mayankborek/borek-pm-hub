import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, applyAuth } from '@/shared/api/client';
import { env } from '@/shared/config/env';

// ---- Role permissions (GET /admin/role-permissions) -------------------------------------------------

/** `always` cannot be switched off; `none` does not apply to the role. */
export type Cell = 'always' | 'on' | 'off' | 'none';

export interface RoleCell {
  key: string;
  label: string;
  section: string;
  value: Cell;
  default: Cell;
  editable: boolean;
}

export interface RoleColumn {
  /** The backend's global role, also the id in the URL. */
  role: string;
  label: string;
  editable: boolean;
  customised: boolean;
  permissions: RoleCell[];
}

export interface RoleMatrix {
  roles: RoleColumn[];
}

const keys = {
  matrix: ['admin', 'role-permissions'] as const,
  projects: (userId: string) => ['admin', 'project-access', userId, 'projects'] as const,
  access: (userId: string, projectId: string) => ['admin', 'project-access', userId, projectId] as const,
  overview: ['admin', 'access-overview'] as const,
};

export const useRoleMatrix = () => useQuery({ queryKey: keys.matrix, queryFn: () => api<RoleMatrix>('/admin/role-permissions') });

/** PUT /admin/role-permissions/{role}/{permission}: saved at once; the response is the whole matrix. */
export function useSetRolePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ role, permission, enabled }: { role: string; permission: string; enabled: boolean }) =>
      api<RoleMatrix>(`/admin/role-permissions/${role}/${permission}`, { method: 'PUT', body: JSON.stringify({ enabled }) }),
    onSuccess: (matrix) => qc.setQueryData(keys.matrix, matrix),
  });
}

/** POST /admin/role-permissions/{role}/reset. */
export function useResetRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (role: string) => api<RoleMatrix>(`/admin/role-permissions/${role}/reset`, { method: 'POST' }),
    onSuccess: (matrix) => qc.setQueryData(keys.matrix, matrix),
  });
}

// ---- A person's switches in one project ---------------------------------------------------------------

export interface PersonRef {
  id: string;
  name: string;
  email: string;
  role: string;
}

export interface PersonProject {
  id: string;
  code: string;
  name: string;
  access: string;
  customised: boolean;
}

export interface PersonProjects {
  person: PersonRef;
  /** False for administrators and client contacts. */
  editable: boolean;
  items: PersonProject[];
}

export interface Control {
  key: string;
  label: string;
  enabled: boolean;
  default: boolean;
  customised: boolean;
  editable: boolean;
  linked_with: string[];
}

export interface Section {
  key: string;
  label: string;
  customised: boolean;
  controls: Control[];
}

export interface PersonProjectAccess {
  person: PersonRef;
  project: { id: string; code: string; name: string };
  access: string;
  sections: Section[];
}

/** GET /admin/people/{user_id}/project-access. */
export const usePersonProjects = (userId: string) =>
  useQuery({ queryKey: keys.projects(userId), queryFn: () => api<PersonProjects>(`/admin/people/${userId}/project-access`), enabled: !!userId });

/** GET /admin/people/{user_id}/project-access/{project_id}. */
export const usePersonProjectAccess = (userId: string, projectId: string) =>
  useQuery({
    queryKey: keys.access(userId, projectId),
    queryFn: () => api<PersonProjectAccess>(`/admin/people/${userId}/project-access/${projectId}`),
    enabled: !!userId && !!projectId,
    placeholderData: keepPreviousData,
  });

function useAccessMutation<V>(userId: string, projectId: string, fn: (v: V) => Promise<PersonProjectAccess>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (screen) => {
      qc.setQueryData(keys.access(userId, projectId), screen);
      // "customised" on the project list may have changed.
      void qc.invalidateQueries({ queryKey: keys.projects(userId) });
    },
  });
}

/** PUT …/project-access/{project_id}/{permission}: returns the whole screen, so every linked switch shows its confirmed state. */
export const useSetProjectControl = (userId: string, projectId: string) =>
  useAccessMutation(userId, projectId, ({ permission, enabled }: { permission: string; enabled: boolean }) =>
    api<PersonProjectAccess>(`/admin/people/${userId}/project-access/${projectId}/${permission}`, { method: 'PUT', body: JSON.stringify({ enabled }) }),
  );

/** POST …/project-access/{project_id}/sections/{section}/reset. */
export const useResetSection = (userId: string, projectId: string) =>
  useAccessMutation(userId, projectId, (section: string) =>
    api<PersonProjectAccess>(`/admin/people/${userId}/project-access/${projectId}/sections/${section}/reset`, { method: 'POST' }),
  );

// ---- Person access overview (GET /access-overview) ------------------------------------------------------

export interface AccessProject {
  project_id: string;
  project_code: string;
  project_name: string;
  project_role: string;
  source: string;
}

export interface AccessPerson {
  id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  projects: AccessProject[];
}

export interface AccessFilter {
  q: string;
  projectId: string;
  personIds: string[];
}

function filterParams({ q, projectId, personIds }: AccessFilter) {
  const p = new URLSearchParams();
  if (q.trim()) p.set('q', q.trim());
  if (projectId) p.append('project_id', projectId);
  for (const id of personIds) p.append('person_id', id);
  return p;
}

/** GET /access-overview: the filtered person-by-project matrix. */
export const useAccessOverview = (filter: AccessFilter) => {
  const p = filterParams(filter);
  p.set('page_size', '200');
  return useQuery({
    queryKey: [...keys.overview, p.toString()],
    queryFn: () => api<{ items: AccessPerson[]; total: number }>(`/access-overview?${p}`),
    placeholderData: keepPreviousData,
  });
};

/** GET /access-overview/export: the whole filtered matrix built by the server. The auth header is needed, so it is saved from a blob. */
export async function downloadAccessExport(filter: AccessFilter, format: 'pdf' | 'csv') {
  const p = filterParams(filter);
  p.set('format', format);
  const headers = new Headers();
  applyAuth(headers);
  const res = await fetch(`${env.apiBaseUrl}/access-overview/export?${p}`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText, await res.json().catch(() => undefined));
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = `person-access.${format}`;
  a.click();
  URL.revokeObjectURL(url);
}
