import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import { qs } from '@/features/projects/projectsApi';

export type AssignableRole = 'admin' | 'pm' | 'developer';
export type StatusFilter = 'all' | 'active' | 'inactive';

export interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  join_date: string | null;
  password_set: boolean;
  invite_pending: boolean;
  projects: { id: string; code: string; name: string }[];
}

interface AdminUserList {
  items: AdminUser[];
  total: number;
  active_total: number;
  page: number;
  page_size: number;
}

/** Shown to the administrator once: the server never returns the link again. */
export interface CreatedUser {
  user: AdminUser;
  invite: { url: string; expires_at: string };
}

export interface UserInput {
  name: string;
  email: string;
  role: AssignableRole;
}

export const ROLE_LABEL: Record<string, string> = {
  admin: 'Administrator',
  pm: 'Project Manager',
  developer: 'Developer',
  manager: 'Manager',
  account_manager: 'Account Manager',
  client: 'Client',
};

export const ASSIGNABLE_ROLES: AssignableRole[] = ['admin', 'pm', 'developer'];

const keys = {
  all: ['admin', 'users'] as const,
  list: (q: string, role: string, status: string) => ['admin', 'users', 'list', q, role, status] as const,
};

/** GET /admin/users (administrator only). */
export const useAdminUsers = (q: string, role: string, status: StatusFilter) =>
  useQuery({
    queryKey: keys.list(q, role, status),
    queryFn: () => api<AdminUserList>(`/admin/users${qs({ q: q.trim(), role, status: status === 'all' ? '' : status, page_size: 100 })}`),
    placeholderData: keepPreviousData,
  });

function useUserMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }) });
}

export const useCreateUser = () =>
  useUserMutation((input: UserInput) => api<CreatedUser>('/admin/users', { method: 'POST', body: JSON.stringify(input) }));

export const useUpdateUser = () =>
  useUserMutation(({ id, ...body }: Partial<UserInput> & { id: string }) =>
    api<AdminUser>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  );

export const useSetUserActive = () =>
  useUserMutation(({ id, active }: { id: string; active: boolean }) =>
    api<AdminUser>(`/admin/users/${id}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' }),
  );

export const useNewInvite = () => useUserMutation((id: string) => api<CreatedUser>(`/admin/users/${id}/invite`, { method: 'POST' }));
