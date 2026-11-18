import { useQuery } from '@tanstack/react-query';
import type { ClientPortalData, ClientProject } from './types';

// The backend has no client-portal endpoints yet, so these hooks serve the supplied design's sample
// data. Replace `fetchPortal` with a call to the real API; the pages only depend on ClientPortalData.
const PM = { name: 'Alex Morgan', role: 'Project Manager' };
const CONTACTS = [{ name: 'Alex Morgan', role: 'Project Manager', email: 'alex.morgan@boreksolutions.com' }];

const SAMPLE: ClientPortalData = {
  today: '2026-11-17',
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
      changeRequests: [{ ref: 'CR-02', title: 'Extend delivery review', status: 'in_review' }],
      reports: [
        {
          id: 'sprint-4-status',
          title: 'Sprint 4 status report',
          periodStart: '2026-10-24',
          periodEnd: '2026-11-01',
          createdOn: '2026-11-02',
          summary: 'Delivery progress is 68%; the delivery review is running late and a revised date is being confirmed.',
          forecast: '2026-11-20',
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
          periodStart: '2026-10-24',
          periodEnd: '2026-10-30',
          createdOn: '2026-10-30',
          summary: 'Delivery progress is 45%; the preview is on track for review.',
          forecast: '2026-11-24',
          progress: 45,
        },
      ],
    },
  ],
};

const fetchPortal = async (): Promise<ClientPortalData> => SAMPLE;

export function useClientPortal() {
  return useQuery({ queryKey: ['client-portal'], queryFn: fetchPortal });
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
