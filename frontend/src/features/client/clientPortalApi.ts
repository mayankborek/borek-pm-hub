import { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import { useAuth } from '@/features/auth/AuthContext';
import type { ClientMilestone, ClientPortalData, ClientProject, MilestoneState } from './types';
import { fetchClientPortal } from './portalMapper';

// Clients read the real portal API (see portalMapper.ts). The Account Manager and Manager screens
// reuse the same pages, but /client/* is closed to them, so they still get the design's sample data
// until their own endpoints exist. The pages only depend on ClientPortalData.
const PM = { name: 'Alex Morgan', role: 'Project Manager' };
const CONTACTS = [
  { name: 'Alex Morgan', role: 'Project Manager', email: 'alex.morgan@boreksolutions.com' },
  { name: 'Jordan Lee', role: 'Client contact', email: 'jordan.lee@customer.com' },
];

const SAMPLE: ClientPortalData = {
  today: todayUtc(), // overridden on every read by useClientPortal
  organisation: 'BRECO',
  notifications: [
    { id: 'n1', headline: 'A progress report is available', meta: 'Website Development', to: '/client/projects/website-development/reports/sprint-4-status', unread: true },
    { id: 'n2', headline: 'Your change request is in review', meta: 'Website Development · CR-02', to: '/client/projects/website-development/change-requests', unread: true },
    { id: 'n3', headline: 'Client handover is coming up', meta: 'Website Development · 20 Nov', to: '/client/projects/website-development/milestones', unread: false },
    { id: 'n4', headline: 'A new report is ready to view', meta: 'Customer portal', to: '/client/projects/customer-portal/reports/delivery-status', unread: false },
  ],
  updates: [
    { id: 'u1', title: 'New report shared', meta: 'Website Development · Latest project update' },
    { id: 'u2', title: 'Change request moved to In review', meta: 'Website Development · Extend delivery review' },
    { id: 'u3', title: 'Milestone schedule published', meta: 'Customer portal · Preview review on 24 Nov' },
  ],
  projects: [
    {
      id: 'website-development',
      code: 'BF-024',
      name: 'Website Development',
      category: 'Web Development',
      health: 'on_track',
      progress: 68,
      startDate: '2026-10-24',
      dueDate: '2026-11-20',
      clientActions: 0,
      note: 'Latest progress shared by your PM',
      latestUpdate: {
        text: 'The delivery review milestone is running late. The revised date is being confirmed; we’ll share it once agreed.',
        date: '2026-11-02',
      },
      publishedOn: '2026-11-02',
      publishedBy: PM,
      contacts: CONTACTS,
      milestones: [
        { id: 'design-signoff', code: 'M-01', name: 'Design sign-off', dueDate: '2026-10-30', state: 'done', progress: 100 },
        { id: 'delivery-review', code: 'M-02', name: 'Delivery review', dueDate: '2026-11-12', state: 'late', progress: 68, changeRequestRef: 'CR-02' },
        { id: 'content-migration', code: 'M-03', name: 'Content migration', dueDate: '2026-11-16', state: 'in_progress', progress: 40 },
        { id: 'client-handover', code: 'M-04', name: 'Client handover', dueDate: '2026-11-20', state: 'planned', progress: 0 },
      ],
      tasks: [
        { id: 't1', title: 'Homepage wireframes', status: 'In progress', dueDate: '2026-10-18' },
        { id: 't2', ref: 'BFL-112', title: 'API credentials', status: 'Blocked', dueDate: '2026-10-20' },
        { id: 't3', title: 'Approve visual direction', status: 'Code review', dueDate: '2026-10-27' },
        { id: 't4', title: 'Redesign project overview', status: 'In progress', dueDate: '2026-10-28' },
        { id: 't5', ref: 'BFL-121', title: 'Fix sign-in error states', status: 'In progress', dueDate: '2026-10-29' },
        { id: 't6', title: 'Update brand guidelines', status: 'To do', dueDate: '2026-10-30' },
        { id: 't7', title: 'Audit mobile navigation', status: 'Testing', dueDate: '2026-10-31' },
        { id: 't8', title: 'Review homepage copy', status: 'To do', dueDate: '2026-11-02' },
      ],
      changeRequests: [{ ref: 'CR-02', title: 'Extend delivery review', status: 'in_review' }],
      reports: [
        {
          id: 'sprint-4-status',
          title: 'Sprint 4 status report',
          reportDate: '2026-11-01',
          publishedAt: '2026-11-02T09:00:00Z',
          health: 'on_track',
          summary: 'Delivery progress is 68%; the delivery review is running late and a revised date is being confirmed.',
          progress: 68,
        },
      ],
    },
    {
      id: 'customer-portal',
      code: 'BF-031',
      name: 'Customer portal',
      category: 'Software',
      health: 'on_track',
      progress: 45,
      startDate: '2026-10-24',
      dueDate: '2026-11-24',
      clientActions: 0,
      publishedOn: '2026-11-02',
      publishedBy: PM,
      contacts: CONTACTS,
      milestones: [
        { id: 'preview-review', code: 'M-01', name: 'Preview review', dueDate: '2026-11-24', state: 'planned', progress: 0 },
        { id: 'client-handover', code: 'M-02', name: 'Client handover', dueDate: '2026-11-30', state: 'planned', progress: 0 },
      ],
      changeRequests: [],
      reports: [
        {
          id: 'delivery-status',
          title: 'Delivery status report',
          reportDate: '2026-10-30',
          publishedAt: '2026-10-30T09:00:00Z',
          health: 'on_track',
          summary: 'Delivery progress is 45%; the preview is on track for review.',
          progress: 45,
        },
      ],
    },
  ],
};

const fetchSample = async (): Promise<ClientPortalData> => SAMPLE;

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
  const isClient = useAuth().user?.role === 'client';
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
    queryKey: ['client-portal', isClient ? 'api' : 'sample'],
    queryFn: isClient ? () => fetchClientPortal(api) : fetchSample,
    select,
    // Pick up newly published reports, milestones and requirements without a reload.
    refetchInterval: isClient ? 60_000 : false,
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
