import { useState } from 'react';
import { useAuth } from '@/features/auth/AuthContext';
import { useToast } from '@/shared/ui/Toast';
import { HEALTH_LABEL } from './labels';
import { downloadReportPdf, downloadSharedReportPdf, useClientReport, useClientSharedReport, useClientSharedReports, type SharedReportDetail } from './reportsApi';
import { Link, useParams } from 'react-router-dom';
import { usePortalPaths } from './portalPaths';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { longDate, paddedDate, pct } from './format';
import { Icon } from './icons';
import { useProjectContext } from './ClientProjectLayout';
import { EmptyCard } from './ui';
import './clientScreens.css';

const backIcon = (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <path d="M10.5 6H1.5M5 2.5L1.5 6 5 9.5" stroke="#124F94" strokeWidth="1.4" />
  </svg>
);

export function ClientReportsPage() {
  const pp = usePortalPaths();
  const isClient = useAuth().user?.role === 'client';
  const toast = useToast();
  const { project } = useProjectContext();
  const { t, lang } = usePrefs();
  const [search, setSearch] = useState('');
  const sharedList = useClientSharedReports(project.id);

  const q = search.trim().toLowerCase();
  const shown = project.reports.filter((r) => !q || r.title.toLowerCase().includes(q));
  const shared = (sharedList.data?.items ?? []).filter((r) => !q || r.title.toLowerCase().includes(q));
  const total = project.reports.length + (sharedList.data?.total ?? 0);

  return (
    <>
      <section className="cx-rh">
        <h1>{t('Reports')}</h1>
        <p>{t('View reports shared with you by your Project Manager.')}</p>
      </section>
      <div className="cx-rf">
        <span className="cx-rchip">{t('All reports')} <span>{total}</span></span>
        <label className="cx-search">
          <Icon name="search" className="cx-ico cx-14" />
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search reports…')} aria-label={t('Search reports')} />
        </label>
      </div>
      {!total && !sharedList.isPending && <EmptyCard />}
      {!!project.reports.length && (
        <section className="cx-card cx-lib" aria-label={t('Report library')}>
          <div className="cx-lhd"><b>{t('Report library')}</b><span>{project.name}</span></div>
          <div className="cx-cols">
            <span>{t('Report')}</span>
            <span>{t('Report date')}</span>
            <span>{t('Published')}</span>
            <span>{t('Status')}</span>
            <span />
          </div>
          {shown.map((r) => (
            <div className="cx-rr" key={r.id}>
              <div className="cx-nm2">
                <span className="cx-ib"><Icon name="file" className="cx-ico cx-18" /></span>
                <div>
                  <div className="cx-t"><Link to={pp.report(project.id, r.id)}>{r.title}</Link></div>
                  <div className="cx-s">{project.publishedBy ? t('Project status · Shared by {name}', { name: project.publishedBy.name }) : t('Project status')}</div>
                </div>
              </div>
              <div className="cx-d">{paddedDate(lang, r.reportDate)}</div>
              <div className="cx-d">{paddedDate(lang, r.publishedAt.slice(0, 10))}</div>
              <div><span className="cx-st"><i />{t('Published')}</span></div>
              <button type="button" className="cx-btn cx-dl" onClick={() => {
                if (!isClient) return window.print();
                downloadReportPdf(project.id, r.id, r.reportDate).catch(() => toast.error(t('The report could not be downloaded.')));
              }}>
                <Icon name="download" className="cx-ico cx-14" /> {t('Download')}
              </button>
            </div>
          ))}
          <div className="cx-cnt">{t('{n} reports', { n: shown.length })}</div>
        </section>
      )}
      {!!shared.length && (
        <section className="cx-card cx-lib" aria-label={t('Shared reports')} style={{ marginTop: 16 }}>
          <div className="cx-lhd"><b>{t('Shared reports')}</b><span>{project.name}</span></div>
          <div className="cx-cols">
            <span>{t('Report')}</span>
            <span>{t('Period')}</span>
            <span>{t('Shared')}</span>
            <span>{t('Prepared by')}</span>
            <span />
          </div>
          {shared.map((r) => (
            <div className="cx-rr" key={r.id}>
              <div className="cx-nm2">
                <span className="cx-ib"><Icon name="file" className="cx-ico cx-18" /></span>
                <div>
                  <div className="cx-t"><Link to={pp.report(project.id, r.id)}>{r.title}</Link></div>
                  <div className="cx-s">{t(KIND_LABEL[r.kind])}</div>
                </div>
              </div>
              <div className="cx-d">{periodLabel(lang, r, t('Overall'))}</div>
              <div className="cx-d">{r.shared_at ? paddedDate(lang, r.shared_at.slice(0, 10)) : '–'}</div>
              <div className="cx-d">{r.prepared_by}</div>
              <button type="button" className="cx-btn cx-dl" onClick={() => downloadSharedReportPdf(project.id, r.id, r.title).catch(() => toast.error(t('The report could not be downloaded.')))}>
                <Icon name="download" className="cx-ico cx-14" /> {t('Download')}
              </button>
            </div>
          ))}
        </section>
      )}
    </>
  );
}

const KIND_LABEL: Record<SharedReportDetail['kind'], string> = {
  tasks: 'Tasks report',
  milestones: 'Milestones report',
  change_requests: 'Change requests report',
  project_status: 'Project status report',
  other: 'Report',
};

const periodLabel = (lang: Parameters<typeof longDate>[0], r: { period_start: string | null; period_end: string | null }, overall: string) =>
  r.period_start && r.period_end ? `${longDate(lang, r.period_start)} – ${longDate(lang, r.period_end)}` : overall;

/** A generated report the project team shared with the client: the same key figures, facts and tables as the PDF. */
function SharedReportView({ projectId, report }: { projectId: string; report: SharedReportDetail }) {
  const pp = usePortalPaths();
  const { t, lang } = usePrefs();
  const toast = useToast();
  const c = report.content;
  return (
    <div className="cp-rd">
      <Link className="cp-back" to={pp.reports(projectId)}>
        {backIcon}
        {t('Back')}
      </Link>
      <h2>{report.title}</h2>
      <div className="cp-card">
        <div className="cp-val" style={{ marginTop: 0, fontSize: 'var(--fs-12)' }}>{t('Prepared by {name}', { name: report.prepared_by })}</div>
        <div className="cp-lbl">{t('Reporting period')}</div>
        <div className="cp-val" style={{ marginTop: 12 }}>{periodLabel(lang, report, t('Overall'))}</div>
        {report.shared_at && (
          <>
            <div className="cp-lbl">{t('Shared on')}</div>
            <div className="cp-val" style={{ marginTop: 12 }}>{longDate(lang, report.shared_at.slice(0, 10))}</div>
          </>
        )}
        {c.facts.map((f) => (
          <div key={f.key}>
            <div className="cp-lbl">{t(f.label)}</div>
            <div className="cp-val" style={{ marginTop: 12 }}>{f.value}</div>
          </div>
        ))}
        {c.kpis.map((k) => (
          <div key={k.key}>
            <div className="cp-lbl">{t(k.label)}</div>
            <div className="cp-big">{k.value}</div>
          </div>
        ))}
        {c.distribution.some((d) => d.count > 0) && (
          <div>
            <div className="cp-lbl">{t('By status')}</div>
            <div className="cp-val" style={{ marginTop: 12 }}>{c.distribution.filter((d) => d.count > 0).map((d) => `${t(d.label)} ${d.count}`).join(' · ')}</div>
          </div>
        )}
        {report.summary && (
          <div>
            <div className="cp-lbl">{t('Summary')}</div>
            <div className="cp-val" style={{ marginTop: 12, whiteSpace: 'pre-line' }}>{report.summary}</div>
          </div>
        )}
        {c.tables.map((tb) => (
          <div key={tb.key} style={{ overflowX: 'auto' }}>
            <div className="cp-lbl">{t(tb.heading)}</div>
            <table style={{ width: '100%', marginTop: 12, fontSize: 'var(--fs-12)', textAlign: 'left' }}>
              <thead><tr>{tb.columns.map((col) => <th key={col}>{t(col)}</th>)}</tr></thead>
              <tbody>
                {tb.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}
              </tbody>
            </table>
          </div>
        ))}
        <div style={{ marginTop: 16 }}>
          <button type="button" className="cx-btn cx-dl" onClick={() => downloadSharedReportPdf(projectId, report.id, report.title).catch(() => toast.error(t('The report could not be downloaded.')))}>
            <Icon name="download" className="cx-ico cx-14" /> {t('Download')}
          </button>
        </div>
        <div className="cp-note">{t('Shared with your client organisation. Internal comments and working drafts are excluded.')}</div>
      </div>
    </div>
  );
}

export function ClientReportPage() {
  const pp = usePortalPaths();
  const { reportId } = useParams();
  const { project } = useProjectContext();
  const { t, lang } = usePrefs();
  const report = project.reports.find((r) => r.id === reportId);
  const detail = useClientReport(project.id, report?.id).data;
  const by = detail?.published_by ?? project.publishedBy;
  const shared = useClientSharedReport(project.id, report ? undefined : reportId);

  if (!report && shared.data) return <SharedReportView projectId={project.id} report={shared.data} />;
  if (!report && shared.isPending && shared.fetchStatus !== 'idle') return <p className="cp-empty">{t('Loading…')}</p>;
  if (!report) {
    return (
      <EmptyCard
        title="Report not found"
        text="This report does not exist or has not been shared with you."
        action={<Link to={pp.reports(project.id)}>{t('Back')}</Link>}
      />
    );
  }

  return (
    <div className="cp-rd">
      <Link className="cp-back" to={pp.reports(project.id)}>
        {backIcon}
        {t('Back')}
      </Link>
      <h2>{report.title}</h2>
      <div className="cp-card">
        {by && (
          <div className="cp-val" style={{ marginTop: 0, fontSize: 'var(--fs-12)' }}>
            {t('Published by {name} · {role}', { name: by.name, role: t(by.role) })}
          </div>
        )}
        <div className="cp-lbl">{t('Report date')}</div>
        <div className="cp-val" style={{ marginTop: 12 }}>{longDate(lang, report.reportDate)}</div>
        <div className="cp-lbl">{t('Published on')}</div>
        <div className="cp-val" style={{ marginTop: 12 }}>{longDate(lang, report.publishedAt.slice(0, 10))}</div>
        <div className="cp-lbl">{t('Project status')}</div>
        <div className="cp-val" style={{ marginTop: 12 }}>{t(HEALTH_LABEL[report.health])}</div>
        <div className="cp-lbl">{t('Published progress')}</div>
        <div className="cp-big">{pct(report.progress)}</div>
        <div className="cp-lbl" style={{ marginTop: 14 }}>{t('Delivery summary')}</div>
        <div className="cp-val" style={{ marginTop: 12 }}>{report.summary}</div>
        {([['Achievements', detail?.achievements], ['Next steps', detail?.next_steps], ['Risks', detail?.risks]] as const).map(
          ([label, text]) =>
            text && (
              <div key={label}>
                <div className="cp-lbl">{t(label)}</div>
                <div className="cp-val" style={{ marginTop: 12, whiteSpace: 'pre-line' }}>{text}</div>
              </div>
            ),
        )}
        <div className="cp-note">{t('Shared with your client organisation. Internal comments and working drafts are excluded.')}</div>
      </div>
    </div>
  );
}
