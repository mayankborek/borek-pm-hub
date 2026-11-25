import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

export type MilestoneState = 'done' | 'late' | 'revised' | 'at_risk' | 'in_progress' | 'planned';

/** Mirrors backend MilestoneOut (app/milestones/schemas.py), the fields the roadmap uses. */
export interface Milestone {
  id: string;
  phase_id: string | null;
  code: string;
  name: string;
  due_date: string;
  state: MilestoneState;
  done: boolean;
  progress: number | null;
  owner: { id: string; name: string } | null;
}

export interface RoadmapPhase {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: 'not_started' | 'in_progress' | 'completed';
  is_late: boolean;
  progress: number | null;
  milestones: Milestone[];
}

/** Mirrors backend RoadmapOut: everything the roadmap draws, in one call. */
export interface Roadmap {
  today: string;
  range_start: string | null;
  range_end: string | null;
  phases: RoadmapPhase[];
  unphased_milestones: Milestone[];
}

export interface MilestoneInput {
  name: string;
  due_date: string;
  phase_id?: string | null;
  owner_id?: string | null;
  at_risk?: boolean;
  client_visible?: boolean;
}

export const roadmapKey = (projectId: string) => ['projects', 'roadmap', projectId] as const;

export const useRoadmap = (projectId: string) =>
  useQuery({ queryKey: roadmapKey(projectId), queryFn: () => api<Roadmap>(`/projects/${projectId}/roadmap`), enabled: !!projectId });

export const useCreateMilestone = (projectId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: MilestoneInput) => api<Milestone>(`/projects/${projectId}/milestones`, { method: 'POST', body: JSON.stringify(input) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: roadmapKey(projectId) }),
  });
};

/** The soonest milestone that is not reached yet, across phases and unphased ones. */
export function nextMilestone(r: Roadmap | undefined): Milestone | undefined {
  if (!r) return undefined;
  return [...r.phases.flatMap((p) => p.milestones), ...r.unphased_milestones].filter((m) => !m.done).sort((a, b) => a.due_date.localeCompare(b.due_date))[0];
}
