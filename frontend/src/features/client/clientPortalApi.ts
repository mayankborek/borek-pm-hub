import { useQuery } from '@tanstack/react-query';
import type { ClientPortalData, ClientProject } from './types';

// The backend has no client-portal endpoints yet, so these hooks serve the supplied design's sample
// data. Replace `fetchPortal` with a call to the real API; the pages only depend on ClientPortalData.
const SAMPLE: ClientPortalData = {
  today: '2026-11-02',
  notifications: [
    { id: 'n1', headline: 'A progress report is available', meta: 'Website Redesign', to: '/client/projects/website-redesign/reports/delivery-status', unread: true },
    { id: 'n2', headline: 'Your change request is in review', meta: 'Website Redesign · CR-02', to: '/client/projects/website-redesign/change-requests', unread: true },
    { id: 'n3', headline: 'Client handover is coming up', meta: 'Website Redesign · 06 Nov', to: '/client/projects/website-redesign/milestones', unread: false },
    { id: 'n4', headline: 'A new report is ready to view', meta: 'Customer portal', to: '/client/projects/customer-portal/reports/delivery-status', unread: false },
  ],
  projects: [
    {
      id: 'website-redesign',
      name: 'Website Redesign',
      health: 'on_track',
      progress: 68,
      publishedOn: '2026-11-02',
      publishedBy: { name: 'Alex Morgan', role: 'Project Manager' },
      contacts: [{ name: 'Alex Morgan', role: 'Project Manager', email: 'alex.morgan@boreksolutions.com' }],
      milestones: [
        {
          id: 'delivery-review',
          code: 'M-01',
          name: 'Delivery review',
          dueDate: '2026-10-30',
          state: 'late',
          progress: 68,
          requestedDate: '2026-11-02',
          changeRequestRef: 'CR-02',
        },
        { id: 'client-handover', code: 'M-02', name: 'Client handover', dueDate: '2026-11-06', state: 'planned', progress: 0 },
      ],
      changeRequests: [{ ref: 'CR-02', title: 'Extend delivery review', status: 'in_review' }],
      reports: [
        {
          id: 'delivery-status',
          title: 'Delivery status report',
          periodStart: '2026-10-24',
          periodEnd: '2026-10-30',
          createdOn: '2026-10-30',
          summary:
            'The project overview is ready for client review. Delivery progress is 68%; the current milestone forecast is 30 Oct 2026.',
          forecast: '2026-10-30',
          progress: 68,
        },
      ],
    },
    {
      id: 'customer-portal',
      name: 'Customer portal',
      health: 'on_track',
      progress: 45,
      publishedOn: '2026-11-02',
      publishedBy: { name: 'Alex Morgan', role: 'Project Manager' },
      contacts: [{ name: 'Alex Morgan', role: 'Project Manager', email: 'alex.morgan@boreksolutions.com' }],
      milestones: [
        { id: 'preview-review', code: 'M-01', name: 'Preview review', dueDate: '2026-11-09', state: 'planned', progress: 0 },
        { id: 'client-handover', code: 'M-02', name: 'Client handover', dueDate: '2026-11-13', state: 'planned', progress: 0 },
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
          forecast: '2026-11-09',
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
