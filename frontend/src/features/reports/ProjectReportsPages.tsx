import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Pill, type Tone } from '@/shared/ui/Pill';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { useProjectContext } from '@/features/projects/ProjectLayout';
import {
  downloadStaffReportPdf,
  useCreateReport,
  usePublishReport,
  useStaffReport,
  useStaffReports,
  useUpdateReport,
  type Rag,
  type ReportDraft,
  type StaffReport,
} from './reportsStaffApi';
import './reports.css';

const RAG: Record<Rag, { label: string; tone: Tone }> = {
  green: { label: 'On track', tone: 'track' },
  amber: { label: 'At risk', tone: 'risk' },
  red: { label: 'Off track', tone: 'overdue' },
};
const long = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

function StateBadge({ report }: { report: StaffReport }) {
  const { t } = usePrefs();
  return report.state === 'draft' ? (
    <span className="rep-draft"><i />{t('Draft')}</span>
  ) : (
    <Pill tone="track">Shared</Pill>
  );
}

/** Reports tab: the report library with a Generate dialog. Drafts stay with the team until published. */
export function ProjectReportsPage() {
  const project = useProjectContext();
  const { t } = usePrefs();
  const list = useStaffReports(project.id);
  const [filter, setFilter] = useState<'all' | 'draft' | 'published'>('all');
  const [q, setQ] = useState('');
  const [generating, setGenerating] = useState(false);

  if (list.isError) return <ErrorState title="We couldn’t load the reports" onRetry={() => void list.refetch()} />;
  if (!list.data) return <LoadingState title="Loading reports" />;

  const items = list.data.items;
  const count = (s: 'draft' | 'published') => items.filter((r) => r.state === s).length;
  const needle = q.trim().toLowerCase();
  const shown = items.filter(
    (r) => (filter === 'all' || r.state === filter) && (!needle || r.summary.toLowerCase().includes(needle) || r.report_date.includes(needle)),
  );
  const tabs = [['all', 'All reports', items.length], ['draft', 'Drafts', count('draft')], ['published', 'Shared', count('published')]] as const;

  return (
    <section className="rep" aria-label={t('Reports')}>
      <div className="rep-head">
        <div>
          <h2>{t('Reports')}</h2>
          <p>{t('Create, review and share project updates in one place.')}</p>
        </div>
        <button type="button" className="btn" onClick={() => setGenerating(true)}>+ {t('Generate report')}</button>
      </div>

      <div className="req-filters rep-filters" role="tablist" aria-label={t('Filter reports')}>
        {tabs.map(([f, label, n]) => (
          <button key={f} type="button" role="tab" aria-selected={filter === f} className={filter === f ? 'req-on' : undefined} onClick={() => setFilter(f)}>
            {t(label)} <span>{n}</span>
          </button>
        ))}
        <input className="input rep-search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('Search reports…')} aria-label={t('Search reports')} />
      </div>

      {shown.length === 0 ? (
        <EmptyState
          title={items.length === 0 ? 'No reports yet' : 'No reports match'}
          text={items.length === 0 ? 'Generate a report to share progress with the client.' : 'Try another filter or search.'}
        />
      ) : (
        <div className="rep-lib">
          <div className="rep-libh"><b>{t('Report library')}</b><span>{project.name}</span></div>
          <div className="rep-cols"><span>{t('Report')}</span><span>{t('Report date')}</span><span>{t('Created')}</span><span>{t('Status')}</span><span /></div>
          {shown.map((r) => (
            <div className="rep-row" key={r.id}>
              <div className="rep-name">
                <span className="rep-ico" aria-hidden="true">▤</span>
                <div>
                  <div className="rep-ttl">{r.summary.length > 60 ? `${r.summary.slice(0, 60)}…` : r.summary}</div>
                  <div className="rep-sub">{t('Project status')} · {t('Created by {name}', { name: r.author.name })}</div>
                </div>
              </div>
              <span>{long(r.report_date)}</span>
              <span>{long(r.created_at)}</span>
              <span><StateBadge report={r} /></span>
              <Link className="rep-open" to={paths.projectReport(project.id, r.id)}>{t('Open report')} →</Link>
            </div>
          ))}
          <div className="rep-libf">
            <span>{t(shown.length === 1 ? '1 report' : '{n} reports', { n: shown.length })}</span>
            <span>{t('Drafts are visible to your team until shared.')}</span>
          </div>
        </div>
      )}

      {generating && <ReportDialog projectId={project.id} onClose={() => setGenerating(false)} />}
    </section>
  );
}

function ReportFields({ value, onChange }: { value: ReportDraft; onChange: (v: ReportDraft) => void }) {
  const { t } = usePrefs();
  const set = <K extends keyof ReportDraft>(k: K, v: ReportDraft[K]) => onChange({ ...value, [k]: v });
  return (
    <>
      <label>{t('Summary')}<textarea rows={3} required value={value.summary} onChange={(e) => set('summary', e.target.value)} placeholder={t('Add a short note for this report...')} /></label>
      <div className="rep-two">
        <label>{t('Report date')}<input type="date" value={value.report_date ?? ''} onChange={(e) => set('report_date', e.target.value || undefined)} /></label>
        <label>{t('Health')}
          <select value={value.rag} onChange={(e) => set('rag', e.target.value as Rag)}>
            {(Object.keys(RAG) as Rag[]).map((r) => <option key={r} value={r}>{t(RAG[r].label)}</option>)}
          </select>
        </label>
        <label>{t('Progress (%)')}
          <input type="number" min={0} max={100} value={value.progress_percent ?? ''} onChange={(e) => set('progress_percent', e.target.value === '' ? null : Number(e.target.value))} />
        </label>
      </div>
      <label>{t('Achievements')}<textarea rows={2} value={value.achievements ?? ''} onChange={(e) => set('achievements', e.target.value)} /></label>
      <label>{t('Next steps')}<textarea rows={2} value={value.next_steps ?? ''} onChange={(e) => set('next_steps', e.target.value)} /></label>
      <label>{t('Risks')}<textarea rows={2} value={value.risks ?? ''} onChange={(e) => set('risks', e.target.value)} /></label>
    </>
  );
}

const clean = (d: ReportDraft): ReportDraft => ({
  ...d,
  summary: d.summary.trim(),
  achievements: d.achievements?.trim() || null,
  next_steps: d.next_steps?.trim() || null,
  risks: d.risks?.trim() || null,
});

function ReportDialog({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const navigate = useNavigate();
  const create = useCreateReport(projectId);
  const { name } = useProjectContext();
  const [draft, setDraft] = useState<ReportDraft>({ rag: 'green', progress_percent: null, summary: '', report_date: new Date().toISOString().slice(0, 10) });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(clean(draft), {
      onSuccess: (r) => navigate(paths.projectReport(projectId, r.id)),
      onError: (err) => toast.error(describeApiError(err, t('The report could not be created.'))),
    });
  };

  return (
    <div className="rep-modal-bg" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <form className="rep-modal" role="dialog" aria-label={t('Generate report')} onSubmit={submit}>
        <button type="button" className="rep-x" onClick={onClose} aria-label={t('Close')}>×</button>
        <h2>{t('Generate report')}</h2>
        <p>{t('Create a report from the project updates shared with you.')}</p>
        <div className="rep-projbox"><span>{t('Project')}</span><b>{name}</b></div>
        <ReportFields value={draft} onChange={setDraft} />
        <div className="rep-mact">
          <button type="button" className="rep-link" onClick={onClose}>{t('Cancel')}</button>
          <button type="submit" className="btn" disabled={create.isPending || !draft.summary.trim()}>{create.isPending ? t('Generating…') : t('Generate report')}</button>
        </div>
      </form>
    </div>
  );
}

/** One report as the client will read it, with Download / Send / Edit for the PM. */
export function ProjectReportPage() {
  const { reportId } = useParams();
  const project = useProjectContext();
  const { t } = usePrefs();
  const toast = useToast();
  const query = useStaffReport(project.id, reportId);
  const publish = usePublishReport(project.id, reportId ?? '');
  const [editing, setEditing] = useState(false);
  const [downloading, setDownloading] = useState(false);

  if (query.isError) return <ErrorState title="We couldn’t load this report" onRetry={() => void query.refetch()} />;
  if (!query.data) return <LoadingState title="Loading report" />;
  const r = query.data;
  const s = project.task_summary;

  const onPublish = () =>
    publish.mutate(undefined, {
      onSuccess: () => toast.success(t('Report shared with the client.')),
      onError: (err) => toast.error(describeApiError(err, t('The report could not be shared.'))),
    });
  const onDownload = () => {
    setDownloading(true);
    downloadStaffReportPdf(project.id, r)
      .catch((err) => toast.error(describeApiError(err, t('The report could not be downloaded.'))))
      .finally(() => setDownloading(false));
  };

  return (
    <section className="rep" aria-label={t('Report preview')}>
      <Link className="rep-back" to={paths.projectReports(project.id)}>← {t('All reports')}</Link>
      <div className="rep-head">
        <h2>{t('Report preview')} <StateBadge report={r} /></h2>
        <div className="rep-acts">
          {r.state === 'published' && <button type="button" className="btn secondary" disabled={downloading} onClick={onDownload}>{t('Download report')}</button>}
          {r.state === 'draft' && (
            <>
              <button type="button" className="btn secondary" onClick={() => setEditing((v) => !v)}>{t(editing ? 'Close editor' : 'Edit report')}</button>
              <button type="button" className="btn" disabled={publish.isPending} onClick={onPublish}>{t('Send report')}</button>
            </>
          )}
        </div>
      </div>

      {editing && r.state === 'draft' ? (
        <EditReport projectId={project.id} report={r} onDone={() => setEditing(false)} />
      ) : (
        <article className="rep-paper">
          <div className="rep-eyebrow">{project.name.toUpperCase()}</div>
          <h3>{t('Status report')}</h3>
          <div className="rep-facts">
            <div><span>{t('Report date')}</span>{long(r.report_date)}</div>
            <div><span>{t('Prepared by')}</span>{r.author.name}</div>
            <div><span>{t('Project')}</span>{project.name}</div>
            <div><span>{t('Health')}</span><Pill tone={RAG[r.rag].tone}>{RAG[r.rag].label}</Pill></div>
          </div>
          {s && s.total > 0 && (
            <>
              <h4>{t('Task overview')}</h4>
              <div className="rep-stats">
                <div><b>{s.total}</b><span>{t('Total tasks')}</span></div>
                <div><b className="g">{s.completed}</b><span>{t('Completed')}</span></div>
                <div><b>{s.total - s.completed}</b><span>{t('Remaining')}</span></div>
                <div><b className="bl">{r.progress_percent ?? s.completion_percent}%</b><span>{t('Completion')}</span></div>
              </div>
            </>
          )}
          <h4>{t('Summary')}</h4>
          <p>{r.summary}</p>
          {r.achievements && (<><h4>{t('Achievements')}</h4><p>{r.achievements}</p></>)}
          {r.next_steps && (<><h4>{t('Next steps')}</h4><p>{r.next_steps}</p></>)}
          {r.risks && (<><h4>{t('Risks')}</h4><p>{r.risks}</p></>)}
          <div className="rep-foot">
            <span>Borek Flow · {project.name}</span>
            <span>{r.state === 'draft' ? t('Report preview') : `${t('Shared')} ${r.published_at ? long(r.published_at) : ''}`}</span>
          </div>
        </article>
      )}
    </section>
  );
}

function EditReport({ projectId, report, onDone }: { projectId: string; report: StaffReport; onDone: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const update = useUpdateReport(projectId, report);
  const [draft, setDraft] = useState<ReportDraft>({
    rag: report.rag,
    progress_percent: report.progress_percent,
    summary: report.summary,
    achievements: report.achievements,
    next_steps: report.next_steps,
    risks: report.risks,
    report_date: report.report_date,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    update.mutate(clean(draft), {
      onSuccess: () => {
        toast.success(t('Report saved'));
        onDone();
      },
      onError: (err) => toast.error(describeApiError(err, t('The report could not be saved.'))),
    });
  };
  return (
    <form className="rep-edit" onSubmit={submit}>
      <ReportFields value={draft} onChange={setDraft} />
      <div className="rep-mact">
        <button type="button" className="rep-link" onClick={onDone}>{t('Cancel')}</button>
        <button type="submit" className="btn" disabled={update.isPending || !draft.summary.trim()}>{t('Save report')}</button>
      </div>
    </form>
  );
}
