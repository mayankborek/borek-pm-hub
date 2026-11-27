import { useQuery } from '@tanstack/react-query';
import { api, ApiError, applyAuth } from '@/shared/api/client';
import { env } from '@/shared/config/env';
import { useAuth } from '@/features/auth/AuthContext';
import type { ClientHealth } from './types';

/** GET /client/projects/{id}/reports/{rid}: the published report with its written sections. */
export interface ClientReportDetail {
  id: string;
  title: string;
  report_date: string;
  health: ClientHealth;
  progress: number | null;
  summary: string;
  published_at: string;
  achievements: string | null;
  next_steps: string | null;
  risks: string | null;
  published_by: { name: string; role: string } | null;
}

/** Only clients can read /client/*; the Account Manager and Manager screens keep their sample reports. */
export function useClientReport(projectId: string, reportId: string | undefined) {
  const isClient = useAuth().user?.role === 'client';
  return useQuery({
    queryKey: ['client-report', projectId, reportId],
    enabled: isClient && !!reportId,
    queryFn: () => api<ClientReportDetail>(`/client/projects/${projectId}/reports/${reportId}`),
  });
}

/** The PDF needs the auth header, so it is fetched and saved from a blob rather than linked. */
export async function downloadReportPdf(projectId: string, reportId: string, reportDate: string) {
  const headers = new Headers();
  applyAuth(headers);
  const res = await fetch(`${env.apiBaseUrl}/client/projects/${projectId}/reports/${reportId}/pdf`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = `status-report-${reportDate}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

/** Generated reports a PM shared with the client portal (GET /client/projects/{id}/shared-reports). */
export interface SharedReportBrief {
  id: string;
  kind: 'tasks' | 'milestones' | 'change_requests' | 'project_status' | 'other';
  title: string;
  period_kind: 'custom' | 'weekly' | 'overall';
  period_start: string | null;
  period_end: string | null;
  prepared_by: string;
  shared_at: string | null;
}

export interface SharedReportDetail extends SharedReportBrief {
  project_name: string;
  client_name: string | null;
  summary: string | null;
  content: {
    kpis: { key: string; label: string; value: string }[];
    distribution: { label: string; category: string | null; count: number }[];
    facts: { key: string; label: string; value: string }[];
    tables: { key: string; heading: string; columns: string[]; rows: string[][]; total_rows: number }[];
  };
  generated_at: string;
}

export function useClientSharedReports(projectId: string) {
  const isClient = useAuth().user?.role === 'client';
  return useQuery({
    queryKey: ['client-shared-reports', projectId],
    enabled: isClient && !!projectId,
    queryFn: () => api<{ items: SharedReportBrief[]; total: number }>(`/client/projects/${projectId}/shared-reports`),
  });
}

export function useClientSharedReport(projectId: string, reportId: string | undefined) {
  const isClient = useAuth().user?.role === 'client';
  return useQuery({
    queryKey: ['client-shared-report', projectId, reportId],
    enabled: isClient && !!reportId,
    queryFn: () => api<SharedReportDetail>(`/client/projects/${projectId}/shared-reports/${reportId}`),
  });
}

/** The PDF needs the auth header, so it is fetched and saved from a blob. */
export async function downloadSharedReportPdf(projectId: string, reportId: string, name: string) {
  const headers = new Headers();
  applyAuth(headers);
  const res = await fetch(`${env.apiBaseUrl}/client/projects/${projectId}/shared-reports/${reportId}/pdf`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = `${name}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}
