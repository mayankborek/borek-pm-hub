import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, applyAuth } from '@/shared/api/client';
import { env } from '@/shared/config/env';

/** What the client portal API returns for a change request: no effort hours, no internal people. */
export type CrStatus = 'pending' | 'in_review' | 'approved' | 'declined';

export interface CrItem {
  id: string;
  code: string;
  title: string;
  status: CrStatus;
  description: string;
  reason: string | null;
  milestone: { code: string; name: string } | null;
  requested_date: string | null;
  review_started_at: string | null;
  impact_schedule_days: number | null;
  impact_scope: string | null;
  decision_note: string | null;
  decided_at: string | null;
  submitted_by: string;
  submitted_at: string;
}

export interface CrList {
  items: CrItem[];
  counts: Record<string, number>;
}

export interface CrComment {
  id: string;
  body: string;
  author: string;
  from_client: boolean;
  created_at: string;
}

export interface CrAttachment {
  id: string;
  name: string;
  content_type: string;
  size_bytes: number;
  uploaded_by: string;
  created_at: string;
}

export interface CrMilestone {
  id: string;
  code: string;
  name: string;
  due_date: string;
}

export interface CrDraft {
  title: string;
  description: string;
  reason?: string;
  milestone_id?: string;
  requested_date?: string;
}

interface Roadmap {
  phases: { milestones: CrMilestone[] }[];
  unphased_milestones: CrMilestone[];
}

const base = (projectId: string) => `/client/projects/${projectId}`;
const key = (projectId: string | undefined, ...rest: string[]) => ['client-cr', projectId, ...rest];

/**
 * The portal screens still run on sample data whose project ids are slugs; the API needs the real
 * project id. Until the portal itself is wired to the API, match the project by id or by name.
 */
export function useApiProjectId(project: { id: string; name: string }) {
  const portal = useQuery({
    queryKey: ['client-portal-api'],
    queryFn: () => api<{ projects: { id: string; name: string }[] }>('/client/portal'),
  });
  const id = portal.data?.projects.find((p) => p.id === project.id || p.name === project.name)?.id;
  return { id, isPending: portal.isPending, isError: portal.isError, missing: portal.isSuccess && !id };
}

export const useChangeRequests = (projectId: string | undefined) =>
  useQuery({
    queryKey: key(projectId),
    enabled: !!projectId,
    queryFn: () => api<CrList>(`${base(projectId!)}/change-requests`),
    // Tracking: pick up the team's decisions and replies without a reload.
    refetchInterval: 60_000,
  });

export const useShareableMilestones = (projectId: string | undefined) =>
  useQuery({
    queryKey: key(projectId, 'milestones'),
    enabled: !!projectId,
    queryFn: async () => {
      const r = await api<Roadmap>(`${base(projectId!)}/roadmap`);
      return [...r.phases.flatMap((p) => p.milestones), ...r.unphased_milestones].sort((a, b) =>
        a.due_date.localeCompare(b.due_date),
      );
    },
  });

export function useComments(projectId: string | undefined, requestId: string | undefined) {
  return useQuery({
    queryKey: key(projectId, requestId ?? '', 'comments'),
    enabled: !!projectId && !!requestId,
    queryFn: () => api<CrComment[]>(`${base(projectId!)}/change-requests/${requestId}/comments`),
    refetchInterval: 30_000,
  });
}

export function useAttachments(projectId: string | undefined, requestId: string | undefined) {
  return useQuery({
    queryKey: key(projectId, requestId ?? '', 'files'),
    enabled: !!projectId && !!requestId,
    queryFn: () => api<CrAttachment[]>(`${base(projectId!)}/change-requests/${requestId}/attachments`),
  });
}

/** Raises a request, then uploads any files to it. A failed upload does not undo the request. */
export function useSubmitChangeRequest(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ draft, files }: { draft: CrDraft; files: File[] }) => {
      const created = await api<CrItem>(`${base(projectId!)}/change-requests`, {
        method: 'POST',
        body: JSON.stringify(draft),
      });
      const failed: string[] = [];
      for (const file of files) {
        const form = new FormData();
        form.append('file', file);
        try {
          await api(`${base(projectId!)}/change-requests/${created.id}/attachments`, { method: 'POST', body: form });
        } catch {
          failed.push(file.name);
        }
      }
      return { created, failed };
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key(projectId) }),
  });
}

export function useAddComment(projectId: string | undefined, requestId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) =>
      api<CrComment>(`${base(projectId!)}/change-requests/${requestId}/comments`, {
        method: 'POST',
        body: JSON.stringify({ body }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projectId, requestId, 'comments') }),
  });
}

/** Files need the auth header, so they are fetched and saved from a blob rather than linked. */
export async function downloadAttachment(projectId: string, requestId: string, file: CrAttachment) {
  const headers = new Headers();
  applyAuth(headers);
  const res = await fetch(`${env.apiBaseUrl}${base(projectId)}/change-requests/${requestId}/attachments/${file.id}/download`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = file.name;
  a.click();
  URL.revokeObjectURL(url);
}
