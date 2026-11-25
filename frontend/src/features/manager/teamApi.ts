import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

/** GET /manager/capacity and GET /manager/workload (Manager only). Only the fields the Team screen uses. */
export type CapacityStatus = 'available' | 'near_capacity' | 'overallocated' | 'unavailable' | 'conflict';

export interface PersonRef {
  id: string;
  name: string;
  job_title: string | null;
}
interface ProjectRef {
  id: string;
  code: string;
  name: string;
}
export interface Segment {
  start: string;
  end: string;
  reserved_hours: number;
  total_percent: number | null;
  status: CapacityStatus;
  projects: { project: ProjectRef; percent: number | null }[];
}
export interface PersonCapacity {
  person: PersonRef;
  free_today: boolean;
  next_unallocated_day: string | null;
  has_engagements: boolean;
  segments: Segment[];
}
export interface Capacity {
  today: string;
  summary: { free_today: number; free_within_3_months: number; without_engagements: number };
  people: PersonCapacity[];
}

interface Counts {
  open: number;
  overdue: number;
  effort_pd: number | null;
  unestimated: number;
}
export interface WorkloadProject extends Counts {
  project: ProjectRef;
  client: string | null;
}
export interface WorkloadPerson extends Counts {
  person: PersonRef;
  projects: WorkloadProject[];
}
export interface Workload {
  summary: {
    people_with_open_work: number;
    projects_with_open_work: number;
    open: number;
    overdue: number;
    effort_pd: number;
    unestimated: number;
    most_open: PersonRef | null;
    most_open_count: number;
  };
  people: WorkloadPerson[];
  unassigned: Counts;
}

/** The timeline shows twelve month columns; 56 weeks from this Monday always covers them. */
export const useCapacity = () =>
  useQuery({ queryKey: ['manager-capacity'], queryFn: () => api<Capacity>('/manager/capacity?weeks=56'), refetchInterval: 15_000, refetchOnWindowFocus: true });

export const useWorkload = () =>
  useQuery({ queryKey: ['manager-workload'], queryFn: () => api<Workload>('/manager/workload'), refetchInterval: 15_000, refetchOnWindowFocus: true });
