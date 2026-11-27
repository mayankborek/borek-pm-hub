import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type { Relationship } from './RelatedTaskDrawer';

export type LinkKind = 'blocks' | 'is_blocked_by' | 'relates_to' | 'duplicates' | 'is_duplicated_by' | 'clones' | 'is_cloned_by';

export interface TaskLink {
  id: string;
  kind: LinkKind;
  /** Readable, from this task's side: "is blocked by". */
  label: string;
  task: { id: string; key: string; title: string; status: { id: string; name: string }; assignee: { id: string; name: string } | null };
  created_at: string;
}

/** What the drawer offers, as the API names it. */
export const LINK_KIND: Record<Relationship, LinkKind> = {
  related: 'relates_to',
  blocks: 'blocks',
  blocked_by: 'is_blocked_by',
  duplicates: 'duplicates',
};

/** Link labels the screens translate; anything else the API sends is shown as it is. */
export const LINK_LABEL: Record<LinkKind, string> = {
  blocks: 'Blocks',
  is_blocked_by: 'Blocked by',
  relates_to: 'Related to',
  duplicates: 'Duplicates',
  is_duplicated_by: 'Duplicated by',
  clones: 'Clones',
  is_cloned_by: 'Cloned by',
};

const key = (taskId: string) => ['tasks', 'links', taskId] as const;

/** GET /tasks/{task_id}/links. */
export const useTaskLinks = (taskId: string) => useQuery({ queryKey: key(taskId), queryFn: () => api<TaskLink[]>(`/tasks/${taskId}/links`), enabled: !!taskId });

/** POST /tasks/{task_id}/links (409 LINK_EXISTS when the two tasks are already linked this way). */
export function useAddTaskLink(taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, otherId }: { kind: LinkKind; otherId: string }) =>
      api<TaskLink>(`/tasks/${taskId}/links`, { method: 'POST', body: JSON.stringify({ kind, task_id: otherId }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(taskId) }),
  });
}

/** DELETE /tasks/{task_id}/links/{link_id}. */
export function useRemoveTaskLink(taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => api<void>(`/tasks/${taskId}/links/${linkId}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(taskId) }),
  });
}
