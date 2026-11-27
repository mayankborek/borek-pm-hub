import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import { qs } from '@/features/projects/projectsApi';

export interface Person {
  id: string;
  name: string;
  email: string;
}

export interface OrganisationProject {
  id: string;
  code: string;
  name: string;
  contacts: Person[];
  needs_contact: boolean;
}

export interface Organisation {
  id: string;
  name: string;
  type: 'internal' | 'client';
  archived_at: string | null;
  version: number;
  account_managers: Person[];
  industry: string | null;
  website: string | null;
  primary_contact_email: string | null;
  project_manager: Person | null;
  /** Active projects with their named client contacts. */
  projects: OrganisationProject[];
  contact_count: number;
}

/** The setup details the form edits. Empty strings are sent as null, which clears them. */
export interface OrgDetails {
  industry: string;
  website: string;
  primaryContactEmail: string;
  projectManagerId: string;
}

const detailsBody = (d: OrgDetails) => ({
  industry: d.industry.trim() || null,
  website: d.website.trim() || null,
  primary_contact_email: d.primaryContactEmail.trim() || null,
  project_manager_id: d.projectManagerId || null,
});

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
  useQuery({ queryKey: keys.one(id), queryFn: () => api<Organisation>(`/organisations/${id}`), enabled: !!id });

export const useOrgMembers = (id: string) =>
  useQuery({ queryKey: keys.members(id), queryFn: () => api<{ items: OrgMember[] }>(`/organisations/${id}/members?page_size=100`), enabled: !!id });

function useOrgMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }) });
}

/** POST /organisations: the details and the Account Manager go in the one call. */
export const useCreateOrganisation = () =>
  useOrgMutation(({ name, managerId, details }: { name: string; managerId: string; details: OrgDetails }) =>
    api<Organisation>('/organisations', {
      method: 'POST',
      body: JSON.stringify({ name, type: 'client', account_manager_ids: managerId ? [managerId] : [], ...detailsBody(details) }),
    }),
  );

/** PATCH /organisations/{id} with the version from the last read. */
export const useUpdateOrganisation = () =>
  useOrgMutation(({ org, name, managerId, details }: { org: Organisation; name: string; managerId: string; details: OrgDetails }) =>
    api<Organisation>(`/organisations/${org.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ version: org.version, name, account_manager_ids: managerId ? [managerId] : [], ...detailsBody(details) }),
    }),
  );

/** PUT /organisations/{id}/projects/{project_id}/contacts: the complete list of named client contacts (at least one). */
export const useSetProjectContacts = () =>
  useOrgMutation(({ orgId, projectId, userIds }: { orgId: string; projectId: string; userIds: string[] }) =>
    api<OrganisationProject>(`/organisations/${orgId}/projects/${projectId}/contacts`, { method: 'PUT', body: JSON.stringify({ user_ids: userIds }) }),
  );

export const useAddMember = (orgId: string) =>
  useOrgMutation((input: { name: string; email: string; job_title?: string | null }) =>
    api<CreatedMember>(`/organisations/${orgId}/members`, { method: 'POST', body: JSON.stringify(input) }),
  );

export const useRenewMemberInvite = (orgId: string) =>
  useOrgMutation((userId: string) => api<CreatedMember>(`/organisations/${orgId}/members/${userId}/invite`, { method: 'POST' }));

export const useRemoveMember = (orgId: string) =>
  useOrgMutation((userId: string) => api<OrgMember>(`/organisations/${orgId}/members/${userId}`, { method: 'DELETE' }));

/** Same as `useAddMember`/`useRemoveMember`, for when the organisation is only known at call time (it was just created). */
export const useAddMemberTo = () =>
  useOrgMutation(({ orgId, ...input }: { orgId: string; name: string; email: string; job_title?: string | null }) =>
    api<CreatedMember>(`/organisations/${orgId}/members`, { method: 'POST', body: JSON.stringify(input) }),
  );

export const useRemoveMemberFrom = () =>
  useOrgMutation(({ orgId, userId }: { orgId: string; userId: string }) =>
    api<OrgMember>(`/organisations/${orgId}/members/${userId}`, { method: 'DELETE' }),
  );

/** Active client contacts of one organisation. */
export const useActiveOrgMembers = (id: string) => {
  const q = useOrgMembers(id);
  return { ...q, members: (q.data?.items ?? []).filter((m) => m.status !== 'deactivated') };
};
