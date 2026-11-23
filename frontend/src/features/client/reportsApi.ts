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
