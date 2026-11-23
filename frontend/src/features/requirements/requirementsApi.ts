import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type { Tone } from '@/features/client/labels';

/**
 * Requirements and their acceptance, for both sides: the PM publishes a version (staff API), the
 * client answers that exact version (portal API). Both read the same status, version numbers and
 * recorded answers, so labels live here and are used by both screens.
 */
export type RequirementStatus = 'draft' | 'awaiting_acceptance' | 'changes_requested' | 'accepted' | 'rejected';
export type Decision = 'accepted' | 'changes_requested' | 'rejected';
export type VersionState = 'draft' | 'awaiting_answer' | 'answered' | 'superseded';

export const STATUS: Record<RequirementStatus, { label: string; tone: Tone }> = {
  draft: { label: 'Draft', tone: 'neutral' },
  awaiting_acceptance: { label: 'Awaiting acceptance', tone: 'warning' },
  changes_requested: { label: 'Changes requested', tone: 'info' },
  accepted: { label: 'Accepted', tone: 'success' },
  rejected: { label: 'Rejected', tone: 'danger' },
};
export const DECISION_LABEL: Record<Decision, string> = {
  accepted: 'Accepted',
  changes_requested: 'Changes requested',
  rejected: 'Rejected',
};
export const VERSION_STATE_LABEL: Record<VersionState, string> = {
  draft: 'Draft',
  awaiting_answer: 'Awaiting answer',
  answered: 'Answered',
  superseded: 'Superseded',
};

export interface Person {
  id: string;
  name: string;
}

// --- staff side (/projects/{id}/requirements) --------------------------------------------------

export interface StaffVersion {
  number: number;
  state: VersionState;
  description: string;
  acceptance_criteria: string[];
  change_note: string | null;
  created_by: Person;
  created_at: string;
  published_at: string | null;
  published_by: Person | null;
  response: Decision | null;
  response_comment: string | null;
  responded_by: Person | null;
  responded_at: string | null;
}

export interface Requirement {
  id: string;
  project_id: string;
  code: string;
  title: string;
  owner: Person | null;
  milestone: { id: string; code: string; name: string; due_date: string } | null;
  status: RequirementStatus;
  current_version: number;
  published_version: number | null;
  has_unpublished_changes: boolean;
  versions: StaffVersion[];
  /** Optimistic-lock counter the publish and update calls send back. */
  version: number;
  created_at: string;
  updated_at: string;
}

export interface RequirementList {
  items: Requirement[];
  total: number;
  counts: Record<string, number>;
}

export interface RequirementDraft {
  title: string;
  description: string;
  acceptance_criteria: string[];
}

const staffKey = (projectId: string) => ['requirements', projectId];

export const useRequirements = (projectId: string) =>
  useQuery({
    queryKey: staffKey(projectId),
    queryFn: () => api<RequirementList>(`/projects/${projectId}/requirements`),
    // Tracking: pick up the client's answers without a reload.
    refetchInterval: 30_000,
  });

export function useCreateRequirement(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (draft: RequirementDraft) =>
      api<Requirement>(`/projects/${projectId}/requirements`, { method: 'POST', body: JSON.stringify(draft) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: staffKey(projectId) }),
  });
}

export function useUpdateRequirement(projectId: string, requirement: Requirement) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (draft: RequirementDraft & { change_note?: string }) =>
      api<Requirement>(`/projects/${projectId}/requirements/${requirement.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ ...draft, version: requirement.version }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: staffKey(projectId) }),
  });
}

export function usePublishRequirement(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (requirement: Requirement) =>
      api<Requirement>(`/projects/${projectId}/requirements/${requirement.id}/publish`, {
        method: 'POST',
        body: JSON.stringify({ version: requirement.version }),
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: staffKey(projectId) }),
  });
}

// --- client side (/client/projects/{id}/requirements) ------------------------------------------

export interface ClientVersion {
  number: number;
  state: Exclude<VersionState, 'draft'>;
  description: string;
  acceptance_criteria: string[];
  change_note: string | null;
  published_at: string;
  published_by: string | null;
  response: Decision | null;
  response_comment: string | null;
  responded_by: string | null;
  responded_at: string | null;
}

export interface ClientRequirement {
  id: string;
  code: string;
  title: string;
  status: Exclude<RequirementStatus, 'draft'>;
  awaiting_your_answer: boolean;
  owner: string | null;
  milestone: { code: string; name: string } | null;
  current: ClientVersion;
  history: ClientVersion[];
}

export interface ClientRequirementList {
  items: ClientRequirement[];
  counts: Record<string, number>;
}

export interface ClientAnswer {
  version_number: number;
  decision: Decision;
  comment?: string;
}

const clientKey = (projectId: string | undefined) => ['client-requirements', projectId];

export const useClientRequirements = (projectId: string | undefined) =>
  useQuery({
    queryKey: clientKey(projectId),
    enabled: !!projectId,
    queryFn: () => api<ClientRequirementList>(`/client/projects/${projectId}/requirements`),
    // A newly published version shows up without a reload.
    refetchInterval: 60_000,
  });

export function useRespond(projectId: string, requirementId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (answer: ClientAnswer) =>
      api<ClientRequirement>(`/client/projects/${projectId}/requirements/${requirementId}/response`, {
        method: 'POST',
        body: JSON.stringify(answer),
      }),
    // A 409 means a newer version was published meanwhile: refresh either way.
    // The portal's "Awaiting your input" counts move too.
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: clientKey(projectId) });
      void qc.invalidateQueries({ queryKey: ['client-portal'] });
    },
  });
}
