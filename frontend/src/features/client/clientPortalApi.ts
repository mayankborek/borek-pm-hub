import { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import { useAuth } from '@/features/auth/AuthContext';
import type { ClientMilestone, ClientPortalData, ClientProject, MilestoneState } from './types';
import { fetchClientPortal } from './portalMapper';
import { fetchStaffPortal } from './staffPortalMapper';

// Clients read the portal API (portalMapper.ts). Account Managers and Managers share the screens but
// /client/* is closed to them, so theirs are built from the staff API (staffPortalMapper.ts). The pages
// only depend on ClientPortalData.

/** Today's date (UTC, like the backend's `today()`), as YYYY-MM-DD. */
function todayUtc() {
  return new Date().toISOString().slice(0, 10);
}

/** Re-reads the date every minute so the portal rolls over at midnight without a reload. */
function useToday() {
  const [today, setToday] = useState(todayUtc);
  useEffect(() => {
    const id = setInterval(() => setToday(todayUtc()), 60_000);
    return () => clearInterval(id);
  }, []);
  return today;
}

/** Mirrors the backend: a milestone that is not done and past its due date is late. */
const stateOn = (m: ClientMilestone, today: string): MilestoneState => {
  if (m.state === 'done') return 'done';
  if (m.dueDate < today) return 'late';
  // Not past due yet: a "late" mark from older data no longer applies.
  if (m.state === 'late') return m.requestedDate ? 'revised' : 'in_progress';
  return m.state;
};

export function useClientPortal() {
  const today = useToday();
  const role = useAuth().user?.role;
  const select = useCallback(
    (data: ClientPortalData): ClientPortalData => ({
      ...data,
      today,
      projects: data.projects.map((p) => ({
        ...p,
        milestones: p.milestones.map((m) => ({ ...m, state: stateOn(m, today) })),
      })),
    }),
    [today],
  );
  return useQuery({
    queryKey: ['client-portal', role],
    enabled: role === 'client' || role === 'account_manager' || role === 'manager',
    queryFn: () => (role === 'client' ? fetchClientPortal(api) : fetchStaffPortal(api, role as 'account_manager' | 'manager')),
    select,
    // Pick up newly published reports, milestones and requirements without a reload.
    refetchInterval: 60_000,
  });
}

export function useClientProject(projectId: string | undefined) {
  const q = useClientPortal();
  const project: ClientProject | undefined = q.data?.projects.find((p) => p.id === projectId);
  return { ...q, project, today: q.data?.today };
}

/** The soonest open milestone that is still ahead of `today`, or undefined when nothing is left. */
export const nextMilestone = (p: ClientProject, today: string) =>
  [...p.milestones]
    .filter((m) => m.state !== 'done' && m.dueDate >= today)
    .sort((a, b) => a.dueDate.localeCompare(b.dueDate))[0];
