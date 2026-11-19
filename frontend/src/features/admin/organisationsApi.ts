import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import { qs } from '@/features/projects/projectsApi';

export interface Person {
  id: string;
  name: string;
  email: string;
}

export interface Organisation {
  id: string;
  name: string;
  type: 'internal' | 'client';
  archived_at: string | null;
  version: number;
  account_managers: Person[];
}

export type MemberStatus = 'invited' | 'invite_expired' | 'active' | 'deactivated';

export interface OrgMember {
  id: string;
  name: string;
  email: string;
  status: MemberStatus;
  job_title: string | null;
}

/** Shown to the administrator once: the server never returns the link again. */
export interface CreatedMember {
  member: OrgMember;
  invite: { url: string; expires_at: string };
}

const keys = {
  all: ['admin', 'organisations'] as const,
  list: (q: string) => ['admin', 'organisations', 'list', q] as const,
  one: (id: string) => ['admin', 'organisations', 'one', id] as const,
  members: (id: string) => ['admin', 'organisations', 'members', id] as const,
};

/** GET /organisations: client organisations. */
export const useOrganisations = (q = '') =>
  useQuery({
    queryKey: keys.list(q),
    queryFn: () => api<{ items: Organisation[] }>(`/organisations${qs({ type: 'client', q: q.trim(), page_size: 100 })}`),
    placeholderData: keepPreviousData,
  });

export const useOrganisation = (id: string) =>
  useQuery({ queryKey: keys.one(id), queryFn: () => api<Organisation>(`/organisations/${id}`) });

export const useOrgMembers = (id: string) =>
  useQuery({ queryKey: keys.members(id), queryFn: () => api<{ items: OrgMember[] }>(`/organisations/${id}/members?page_size=100`) });

function useOrgMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }) });
}

const put = (path: string, body: unknown) => api<Person[]>(path, { method: 'PUT', body: JSON.stringify(body) });

/** Creates the organisation, then assigns its Account Manager (if one was chosen). */
export const useCreateOrganisation = () =>
  useOrgMutation(async ({ name, managerId }: { name: string; managerId: string }) => {
    const org = await api<Organisation>('/organisations', { method: 'POST', body: JSON.stringify({ name, type: 'client' }) });
    if (managerId) await put(`/organisations/${org.id}/account-managers`, { user_ids: [managerId] });
    return org;
  });

export const useUpdateOrganisation = () =>
  useOrgMutation(async ({ org, name, managerId }: { org: Organisation; name: string; managerId: string }) => {
    if (name !== org.name) await api<Organisation>(`/organisations/${org.id}`, { method: 'PATCH', body: JSON.stringify({ version: org.version, name }) });
    await put(`/organisations/${org.id}/account-managers`, { user_ids: managerId ? [managerId] : [] });
  });

export const useAddMember = (orgId: string) =>
  useOrgMutation((input: { name: string; email: string; job_title?: string | null }) =>
    api<CreatedMember>(`/organisations/${orgId}/members`, { method: 'POST', body: JSON.stringify(input) }),
  );

export const useRenewMemberInvite = (orgId: string) =>
  useOrgMutation((userId: string) => api<CreatedMember>(`/organisations/${orgId}/members/${userId}/invite`, { method: 'POST' }));

export const useRemoveMember = (orgId: string) =>
  useOrgMutation((userId: string) => api<OrgMember>(`/organisations/${orgId}/members/${userId}`, { method: 'DELETE' }));
