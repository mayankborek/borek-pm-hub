import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type { CrAttachment, CrStatus } from '@/features/client/changeRequestsApi';

/** Staff side of change requests (/projects/{id}/change-requests): the PM queue. Same statuses as the client portal. */
export interface Person {
  id: string;
  name: string;
}

export interface StaffCr {
  id: string;
  project_id: string;
  code: string;
  title: string;
  description: string;
  reason: string | null;
  milestone: { id: string; code: string; name: string; due_date: string } | null;
  requested_date: string | null;
  status: CrStatus;
  review_started_at: string | null;
  impact_schedule_days: number | null;
  impact_effort_hours: number | null;
  impact_scope: string | null;
  decision_note: string | null;
  decided_by: Person | null;
  decided_at: string | null;
  submitted_by: Person;
  submitted_by_client: boolean;
  /** Optimistic-lock counter every change sends back. */
  version: number;
  created_at: string;
  updated_at: string;
}

export interface StaffCrList {
  items: StaffCr[];
  total: number;
  counts: Record<string, number>;
}

export interface StaffComment {
  id: string;
  body: string;
  internal: boolean;
  author: Person;
  author_is_client: boolean;
  created_at: string;
}

export interface ImpactDraft {
  impact_schedule_days: number | null;
  impact_effort_hours: number | null;
  impact_scope: string | null;
}

const base = (projectId: string) => `/projects/${projectId}/change-requests`;
const key = (projectId: string | undefined, ...rest: string[]) => ['staff-cr', projectId, ...rest];

export const useStaffChangeRequests = (projectId: string | undefined) =>
  useQuery({
    queryKey: key(projectId),
    enabled: !!projectId,
    queryFn: () => api<StaffCrList>(base(projectId!)),
    // New client submissions show up in the queue without a reload.
    refetchInterval: 30_000,
  });

/** Number of requests waiting for the PM to start a review; feeds the tab badge. */
export function usePendingChangeRequests(projectId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: key(projectId),
    enabled: enabled && !!projectId,
    queryFn: () => api<StaffCrList>(base(projectId!)),
    refetchInterval: 30_000,
    select: (d) => d.counts.pending ?? 0,
  });
}

export const useStaffComments = (projectId: string, requestId: string) =>
  useQuery({
    queryKey: key(projectId, requestId, 'comments'),
    queryFn: () => api<StaffComment[]>(`${base(projectId)}/${requestId}/comments`),
    refetchInterval: 30_000,
  });

export const useStaffAttachments = (projectId: string, requestId: string) =>
  useQuery({
    queryKey: key(projectId, requestId, 'files'),
    queryFn: () => api<CrAttachment[]>(`${base(projectId)}/${requestId}/attachments`),
  });

/** A 409 means someone else changed the request meanwhile: refresh either way. */
function useAction<T>(projectId: string, run: (v: T) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: run, onSettled: () => qc.invalidateQueries({ queryKey: key(projectId) }) });
}

export const useStartReview = (projectId: string, cr: StaffCr) =>
  useAction<void>(projectId, () =>
    api(`${base(projectId)}/${cr.id}/start-review`, { method: 'POST', body: JSON.stringify({ version: cr.version }) }),
  );

export const useSaveImpact = (projectId: string, cr: StaffCr) =>
  useAction<ImpactDraft>(projectId, (impact) =>
    api(`${base(projectId)}/${cr.id}`, { method: 'PATCH', body: JSON.stringify({ version: cr.version, ...impact }) }),
  );

export const useDecide = (projectId: string, cr: StaffCr) =>
  useAction<{ decision: 'approved' | 'declined'; note?: string }>(projectId, (d) =>
    api(`${base(projectId)}/${cr.id}/decision`, { method: 'POST', body: JSON.stringify({ version: cr.version, ...d }) }),
  );

export function useStaffAddComment(projectId: string, requestId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (c: { body: string; internal: boolean }) =>
      api<StaffComment>(`${base(projectId)}/${requestId}/comments`, { method: 'POST', body: JSON.stringify(c) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projectId, requestId, 'comments') }),
  });
}
