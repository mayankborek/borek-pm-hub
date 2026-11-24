import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, applyAuth } from '@/shared/api/client';
import { env } from '@/shared/config/env';

/** Staff side of status reports (/projects/{id}/status-reports): drafts and published, newest first. */
export type Rag = 'green' | 'amber' | 'red';

export interface StaffReport {
  id: string;
  project_id: string;
  rag: Rag;
  progress_percent: number | null;
  summary: string;
  achievements: string | null;
  next_steps: string | null;
  risks: string | null;
  report_date: string;
  state: 'draft' | 'published';
  published_at: string | null;
  published_by: { id: string; name: string } | null;
  author: { id: string; name: string };
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ReportDraft {
  rag: Rag;
  progress_percent: number | null;
  summary: string;
  achievements?: string | null;
  next_steps?: string | null;
  risks?: string | null;
  report_date?: string;
}

const base = (projectId: string) => `/projects/${projectId}/status-reports`;
const key = (projectId: string | undefined, ...rest: string[]) => ['staff-reports', projectId, ...rest];

export const useStaffReports = (projectId: string) =>
  useQuery({
    queryKey: key(projectId),
    queryFn: () => api<{ items: StaffReport[]; total: number }>(`${base(projectId)}?page_size=100`),
  });

export const useStaffReport = (projectId: string, reportId: string | undefined) =>
  useQuery({
    queryKey: key(projectId, reportId ?? ''),
    enabled: !!reportId,
    queryFn: () => api<StaffReport>(`${base(projectId)}/${reportId}`),
  });

export function useCreateReport(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: ReportDraft) => api<StaffReport>(base(projectId), { method: 'POST', body: JSON.stringify(d) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projectId) }),
  });
}

export function useUpdateReport(projectId: string, report: StaffReport) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: Partial<ReportDraft>) =>
      api<StaffReport>(`${base(projectId)}/${report.id}`, { method: 'PATCH', body: JSON.stringify({ version: report.version, ...d }) }),
    onSettled: () => qc.invalidateQueries({ queryKey: key(projectId) }),
  });
}

export function usePublishReport(projectId: string, reportId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<StaffReport>(`${base(projectId)}/${reportId}/publish`, { method: 'POST' }),
    onSettled: () => qc.invalidateQueries({ queryKey: key(projectId) }),
  });
}

/** The PDF needs the auth header, so it is fetched and saved from a blob. */
export async function downloadStaffReportPdf(projectId: string, report: StaffReport) {
  const headers = new Headers();
  applyAuth(headers);
  const res = await fetch(`${env.apiBaseUrl}${base(projectId)}/${report.id}/pdf`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = `status-report-${report.report_date}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}
