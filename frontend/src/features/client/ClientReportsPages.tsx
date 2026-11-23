import { useState } from 'react';
import { useAuth } from '@/features/auth/AuthContext';
import { useToast } from '@/shared/ui/Toast';
import { HEALTH_LABEL } from './labels';
import { downloadReportPdf, useClientReport } from './reportsApi';
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

  const q = search.trim().toLowerCase();
  const shown = project.reports.filter((r) => !q || r.title.toLowerCase().includes(q));

  return (
    <>
      <section className="cx-rh">
        <h1>{t('Reports')}</h1>
        <p>{t('View reports shared with you by your Project Manager.')}</p>
      </section>
      <div className="cx-rf">
        <span className="cx-rchip">{t('All reports')} <span>{project.reports.length}</span></span>
        <label className="cx-search">
          <Icon name="search" className="cx-ico cx-14" />
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search reports…')} aria-label={t('Search reports')} />
        </label>
      </div>
      {!project.reports.length ? (
        <EmptyCard />
      ) : (
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
    </>
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

/** Change Requests and Contacts have no supplied design yet; the design itself shows this notice. */
export function ClientPlaceholderPage() {
  const { t } = usePrefs();
  return <p className="cp-empty">{t('This section isn’t part of the supplied designs yet.')}</p>;
}
