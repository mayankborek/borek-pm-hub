import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, applyAuth } from '@/shared/api/client';
import { env } from '@/shared/config/env';

/** Staff side of generated reports (/projects/{id}/reports): a snapshot of project data for a type and a period. */
export type ReportKind = 'tasks' | 'milestones' | 'change_requests' | 'project_status' | 'other';
export type PeriodKind = 'custom' | 'weekly' | 'overall';
export type Audience = 'account_manager' | 'client' | 'manager';

export interface ReportBrief {
  id: string;
  project_id: string;
  kind: ReportKind;
  title: string;
  period_kind: PeriodKind;
  period_start: string | null;
  period_end: string | null;
  prepared_by: { id: string; name: string };
  generated_at: string;
  shared_with: Audience[];
  shared_at: string | null;
  version: number;
  created_at: string;
}

export interface ReportContent {
  kpis: { key: string; label: string; value: string }[];
  distribution: { label: string; category: string | null; count: number }[];
  facts: { key: string; label: string; value: string }[];
  tables: { key: string; heading: string; columns: string[]; rows: string[][]; total_rows: number }[];
}

export interface StaffReport extends ReportBrief {
  project_name: string;
  project_code: string;
  client_name: string | null;
  summary: string | null;
  content: ReportContent;
}

/** Body of Generate (POST) and Edit (PUT, plus `version`). */
export interface ReportSettings {
  kind: ReportKind;
  period_kind?: PeriodKind;
  period_start?: string | null;
  period_end?: string | null;
  title?: string | null;
  summary?: string | null;
}

const base = (projectId: string) => `/projects/${projectId}/reports`;
const key = (projectId: string | undefined, ...rest: string[]) => ['staff-reports', projectId, ...rest];

export const useStaffReports = (projectId: string) =>
  useQuery({
    queryKey: key(projectId),
    queryFn: () => api<{ items: ReportBrief[]; total: number }>(`${base(projectId)}?page_size=100`),
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
    mutationFn: (d: ReportSettings) => api<StaffReport>(base(projectId), { method: 'POST', body: JSON.stringify(d) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projectId) }),
  });
}

export function useUpdateReport(projectId: string, report: ReportBrief) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (d: ReportSettings) =>
      api<StaffReport>(`${base(projectId)}/${report.id}`, { method: 'PUT', body: JSON.stringify({ version: report.version, ...d }) }),
    onSettled: () => qc.invalidateQueries({ queryKey: key(projectId) }),
  });
}

/** Send report: the full list of audiences that can view it ([] stops sharing). */
export function useShareReport(projectId: string, report: ReportBrief) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (audiences: Audience[]) =>
      api<StaffReport>(`${base(projectId)}/${report.id}/share`, { method: 'POST', body: JSON.stringify({ version: report.version, audiences }) }),
    onSettled: () => qc.invalidateQueries({ queryKey: key(projectId) }),
  });
}

/** The PDF needs the auth header, so it is fetched and saved from a blob. */
export async function downloadStaffReportPdf(projectId: string, report: ReportBrief) {
  const headers = new Headers();
  applyAuth(headers);
  const res = await fetch(`${env.apiBaseUrl}${base(projectId)}/${report.id}/pdf`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = `${report.kind}-report-${report.generated_at.slice(0, 10)}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}
