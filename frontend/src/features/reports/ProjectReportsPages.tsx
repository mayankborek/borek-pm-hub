import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { useProjectContext } from '@/features/projects/ProjectLayout';
import {
  downloadStaffReportPdf,
  useCreateReport,
  useShareReport,
  useStaffReport,
  useStaffReports,
  useUpdateReport,
  type Audience,
  type PeriodKind,
  type ReportBrief,
  type ReportKind,
  type ReportSettings,
  type StaffReport,
} from './reportsStaffApi';
import './reports.css';

const KIND_LABEL: Record<ReportKind, string> = {
  tasks: 'Task report',
  milestones: 'Milestone report',
  change_requests: 'Change request report',
  project_status: 'Project status report',
  other: 'Custom report',
};
const KINDS = Object.keys(KIND_LABEL) as ReportKind[];
const AUDIENCE_LABEL: Record<Audience, string> = { account_manager: 'Account Manager', client: 'Client', manager: 'Manager' };
const SLICE_COLOR: Record<string, string> = { done: '#17785a', in_progress: '#3b6bdb', todo: '#868a9e', backlog: '#b4b7c6', blocked: '#c43d3d' };
const NAME_COLOR: Record<string, string> = { 'code review': '#7b4fc4', testing: '#e07b00' };

const long = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
const today = () => new Date().toISOString().slice(0, 10);

/** "24–30 Oct 2026", "09 Nov 2026 – 15 Nov 2026" or "Overall". */
function periodText(r: Pick<ReportBrief, 'period_kind' | 'period_start' | 'period_end'>, overall: string) {
  if (!r.period_start || !r.period_end) return overall;
  const [a, b] = [new Date(r.period_start), new Date(r.period_end)];
  return a.getUTCMonth() === b.getUTCMonth() && a.getUTCFullYear() === b.getUTCFullYear() && a.getUTCDate() !== b.getUTCDate()
    ? `${String(a.getUTCDate()).padStart(2, '0')}–${long(r.period_end)}`
    : `${long(r.period_start)} – ${long(r.period_end)}`;
}

const isShared = (r: ReportBrief) => r.shared_with.length > 0;

function StateBadge({ report }: { report: ReportBrief }) {
  const { t } = usePrefs();
  return isShared(report) ? (
    <span className="rep-draft rep-shared"><i />{t('Shared')}</span>
  ) : (
    <span className="rep-draft"><i />{t('Draft')}</span>
  );
}

/** Reports tab: the report library with a Generate dialog. Reports stay with the team until shared. */
export function ProjectReportsPage() {
  const project = useProjectContext();
  const { t } = usePrefs();
  const list = useStaffReports(project.id);
  const [filter, setFilter] = useState<'all' | 'draft' | 'shared'>('all');
  const [q, setQ] = useState('');
  const [generating, setGenerating] = useState(false);

  if (list.isError) return <ErrorState title="We couldn’t load the reports" onRetry={() => void list.refetch()} />;
  if (!list.data) return <LoadingState title="Loading reports" />;

  const items = list.data.items;
  const count = (shared: boolean) => items.filter((r) => isShared(r) === shared).length;
  const needle = q.trim().toLowerCase();
  const shown = items.filter(
    (r) => (filter === 'all' || isShared(r) === (filter === 'shared')) && (!needle || r.title.toLowerCase().includes(needle) || t(KIND_LABEL[r.kind]).toLowerCase().includes(needle)),
  );
  const tabs = [['all', 'All reports', items.length], ['draft', 'Drafts', count(false)], ['shared', 'Shared', count(true)]] as const;

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
          text={items.length === 0 ? 'Generate a report to share progress with the team and the client.' : 'Try another filter or search.'}
        />
      ) : (
        <div className="rep-lib">
          <div className="rep-libh"><b>{t('Report library')}</b><span>{project.name}</span></div>
          <div className="rep-cols"><span>{t('Report')}</span><span>{t('Reporting period')}</span><span>{t('Created')}</span><span>{t('Status')}</span><span /></div>
          {shown.map((r) => (
            <div className="rep-row" key={r.id}>
              <div className="rep-name">
                <span className="rep-ico" aria-hidden="true">▤</span>
                <div>
                  <div className="rep-ttl">{r.title}</div>
                  <div className="rep-sub">{t(KIND_LABEL[r.kind])} · {t('Created by {name}', { name: r.prepared_by.name })}</div>
                </div>
              </div>
              <span>{periodText(r, t('Overall'))}</span>
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

interface Form {
  kind: ReportKind;
  title: string;
  period_kind: PeriodKind;
  start: string;
  end: string;
  summary: string;
}

const toForm = (r?: StaffReport): Form => ({
  kind: r?.kind ?? 'tasks',
  title: r?.title ?? '',
  period_kind: r?.period_kind ?? 'custom',
  start: r?.period_start ?? today().slice(0, 8) + '01',
  end: r?.period_end ?? today(),
  summary: r?.summary ?? '',
});

const toSettings = (f: Form): ReportSettings => ({
  kind: f.kind,
  period_kind: f.period_kind,
  period_start: f.period_kind === 'overall' ? null : f.start,
  period_end: f.period_kind === 'custom' ? f.end : null,
  title: f.title.trim() || null,
  summary: f.summary.trim() || null,
});

/** Generate report (and Edit report, which generates the data again): type, name, reporting period, optional summary. */
function ReportDialog({ projectId, report, onClose, onSaved }: { projectId: string; report?: StaffReport; onClose: () => void; onSaved?: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const navigate = useNavigate();
  const create = useCreateReport(projectId);
  const update = useUpdateReport(projectId, report ?? ({ version: 1, id: '' } as ReportBrief));
  const { name } = useProjectContext();
  const [f, setF] = useState<Form>(() => toForm(report));
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));
  const pending = create.isPending || update.isPending;

  const setKind = (kind: ReportKind) =>
    setF((x) => ({ ...x, kind, period_kind: kind === 'tasks' || kind === 'milestones' || kind === 'change_requests' ? 'custom' : 'overall' }));
  const periods: PeriodKind[] = f.kind === 'project_status' ? ['overall', 'weekly'] : f.kind === 'other' ? ['overall'] : ['custom'];
  const valid = (f.kind !== 'other' || (f.title.trim() && f.summary.trim())) && (f.period_kind === 'overall' || (f.start && (f.period_kind === 'weekly' || (f.end && f.end >= f.start))));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const onError = (err: unknown) => toast.error(describeApiError(err, t(report ? 'The report could not be saved.' : 'The report could not be created.')));
    if (report) update.mutate(toSettings(f), { onSuccess: () => { toast.success(t('Report saved')); onSaved?.(); onClose(); }, onError });
    else create.mutate(toSettings(f), { onSuccess: (r) => navigate(paths.projectReport(projectId, r.id)), onError });
  };

  return (
    <div className="rep-modal-bg" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <form className="rep-modal" role="dialog" aria-label={t(report ? 'Edit report' : 'Generate report')} onSubmit={submit}>
        <button type="button" className="rep-x" onClick={onClose} aria-label={t('Close')}>×</button>
        <h2>{t(report ? 'Edit report' : 'Generate report')}</h2>
        <p>{t('Create a report from the project updates shared with you.')}</p>
        <div className="rep-projbox"><span>{t('Project')}</span><b>{name}</b></div>
        <div className="rep-two">
          <label>{t('Report type')}
            <select value={f.kind} onChange={(e) => setKind(e.target.value as ReportKind)}>
              {KINDS.map((k) => <option key={k} value={k}>{t(KIND_LABEL[k])}</option>)}
            </select>
          </label>
          <label>{f.kind === 'other' ? t('Report name') : `${t('Report name')} (${t('optional')})`}
            <input value={f.title} maxLength={200} onChange={(e) => set('title', e.target.value)} placeholder={t(KIND_LABEL[f.kind])} />
          </label>
        </div>
        <div className="rep-two">
          {periods.length > 1 && (
            <label>{t('Period')}
              <select value={f.period_kind} onChange={(e) => set('period_kind', e.target.value as PeriodKind)}>
                <option value="overall">{t('Whole project')}</option>
                <option value="weekly">{t('Weekly')}</option>
              </select>
            </label>
          )}
          {f.period_kind !== 'overall' && (
            <label>{t(f.period_kind === 'weekly' ? 'Any day of the week' : 'Start')}
              <input type="date" required value={f.start} onChange={(e) => set('start', e.target.value)} />
            </label>
          )}
          {f.period_kind === 'custom' && (
            <label>{t('End')}<input type="date" required min={f.start} value={f.end} onChange={(e) => set('end', e.target.value)} /></label>
          )}
        </div>
        <label>{f.kind === 'other' ? t('Summary') : t('Summary (optional)')}
          <textarea rows={3} value={f.summary} onChange={(e) => set('summary', e.target.value)} placeholder={t('Add a short note for this report...')} />
        </label>
        <div className="rep-mact">
          <button type="button" className="rep-link" onClick={onClose}>{t('Cancel')}</button>
          <button type="submit" className="btn" disabled={pending || !valid}>
            {pending ? t(report ? 'Saving…' : 'Generating…') : t(report ? 'Save report' : 'Generate report')}
          </button>
        </div>
      </form>
    </div>
  );
}

/** Send report: pick who can view it inside the app. Clients exist only on external projects. */
function SendPanel({ projectId, report, external, onClose }: { projectId: string; report: StaffReport; external: boolean; onClose: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const share = useShareReport(projectId, report);
  const [picked, setPicked] = useState<Audience[]>(report.shared_with);
  const options = (Object.keys(AUDIENCE_LABEL) as Audience[]).filter((a) => a !== 'client' || external);
  const toggle = (a: Audience) => setPicked((p) => (p.includes(a) ? p.filter((x) => x !== a) : [...p, a]));

  const send = () =>
    share.mutate(picked, {
      onSuccess: () => {
        toast.success(t(picked.length ? 'Report shared.' : 'Sharing stopped.'));
        onClose();
      },
      onError: (err) => toast.error(describeApiError(err, t('The report could not be shared.'))),
    });

  return (
    <div className="rep-send" role="group" aria-label={t('Send report')}>
      <b>{t('Who can view this report?')}</b>
      <div className="rep-aud">
        {options.map((a) => (
          <label key={a}><input type="checkbox" checked={picked.includes(a)} onChange={() => toggle(a)} />{t(AUDIENCE_LABEL[a])}</label>
        ))}
      </div>
      <div className="rep-mact">
        <button type="button" className="rep-link" onClick={onClose}>{t('Cancel')}</button>
        <button type="button" className="btn" disabled={share.isPending} onClick={send}>{t(picked.length ? 'Send report' : 'Stop sharing')}</button>
      </div>
    </div>
  );
}

/** Colour for a status slice: the design's named states, otherwise its category. */
const sliceColor = (label: string, category: string | null) => NAME_COLOR[label.toLowerCase()] ?? SLICE_COLOR[category ?? 'todo'] ?? '#868a9e';

const STATUS_CLASS: Record<string, string> = { Done: 'g', Completed: 'g', Blocked: 'r', Late: 'r', Declined: 'r', 'Code review': 'v', Testing: 'o', 'In progress': 'b', 'In review': 'b' };

/** One report as the team and the client will read it, with Download / Send / Edit for the PM. */
export function ProjectReportPage() {
  const { reportId } = useParams();
  const project = useProjectContext();
  const { t } = usePrefs();
  const toast = useToast();
  const query = useStaffReport(project.id, reportId);
  const [editing, setEditing] = useState(false);
  const [sending, setSending] = useState(false);
  const [downloading, setDownloading] = useState(false);

  if (query.isError) return <ErrorState title="We couldn’t load this report" onRetry={() => void query.refetch()} />;
  if (!query.data) return <LoadingState title="Loading report" />;
  const r = query.data;
  const c = r.content;
  const total = c.distribution.reduce((n, d) => n + d.count, 0);

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
          <button type="button" className="btn secondary" disabled={downloading} onClick={onDownload}>{t('Download report')}</button>
          <button type="button" className="btn" onClick={() => setSending((v) => !v)}>{t('Send report')}</button>
          <button type="button" className="btn secondary" disabled={isShared(r)} title={isShared(r) ? t('Stop sharing to edit this report.') : undefined} onClick={() => setEditing(true)}>{t('Edit report')}</button>
        </div>
      </div>

      {sending && <SendPanel projectId={project.id} report={r} external={project.type === 'external'} onClose={() => setSending(false)} />}
      {editing && <ReportDialog projectId={project.id} report={r} onClose={() => setEditing(false)} />}

      <article className="rep-paper">
        <div className="rep-eyebrow">{project.name.toUpperCase()}</div>
        <h3>{r.title}</h3>
        <div className="rep-facts">
          <div><span>{t('Reporting period')}</span>{periodText(r, t('Overall'))}</div>
          <div><span>{t('Prepared by')}</span>{r.prepared_by.name}</div>
          <div><span>{t('Project')}</span>{project.name}</div>
          {c.facts.map((x) => <div key={x.key}><span>{t(x.label)}</span>{x.value}</div>)}
        </div>

        {c.kpis.length > 0 && (
          <>
            <h4>{t(r.kind === 'tasks' ? 'Task overview' : 'Overview')}</h4>
            <div className="rep-stats">
              {c.kpis.map((k, i) => (
                <div key={k.key}><b className={i === 1 ? 'g' : i === c.kpis.length - 1 && k.value.endsWith('%') ? 'bl' : undefined}>{k.value}</b><span>{t(k.label)}</span></div>
              ))}
            </div>
          </>
        )}

        {total > 0 && (
          <>
            <div className="rep-dist" role="img" aria-label={t('{n} items by status', { n: total })}>
              {c.distribution.filter((d) => d.count > 0).map((d) => <i key={d.label} style={{ flex: d.count, background: sliceColor(d.label, d.category) }} />)}
            </div>
            <ul className="rep-legend">
              {c.distribution.filter((d) => d.count > 0).map((d) => (
                <li key={d.label}><i style={{ background: sliceColor(d.label, d.category) }} />{t(d.label)} {d.count}</li>
              ))}
            </ul>
          </>
        )}

        {r.summary && (<><h4>{t('Summary')}</h4><p>{r.summary}</p></>)}

        {c.tables.map((tb) => (
          <div key={tb.key} className="rep-table">
            <h4>{t(tb.heading)}</h4>
            <div className="rep-tscroll">
              <table>
                <thead><tr>{tb.columns.map((col) => <th key={col}>{t(col)}</th>)}</tr></thead>
                <tbody>
                  {tb.rows.slice(0, 10).map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => {
                        const statusCol = tb.columns[j] === 'Status';
                        return <td key={j} className={statusCol ? `rep-st ${STATUS_CLASS[cell] ?? ''}` : j === 0 ? 'rep-first' : undefined}>{/^\d{4}-\d{2}-\d{2}$/.test(cell) ? long(cell) : cell}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="rep-tnote">
              {t('Showing {n} of {total} · Preview sample', { n: Math.min(10, tb.rows.length), total: tb.total_rows })}
            </p>
          </div>
        ))}
        {!r.summary && c.kpis.length === 0 && c.tables.length === 0 && <p>{t('This report has no content.')}</p>}

        <div className="rep-foot">
          <span>Borek Flow · {project.name}</span>
          <span>{isShared(r) ? `${t('Shared')} ${r.shared_at ? long(r.shared_at) : ''}` : t('Report preview')}</span>
        </div>
      </article>
    </section>
  );
}
