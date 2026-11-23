import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { usePortalPaths } from './portalPaths';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { dateRange, longDate, paddedDate } from './format';
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
            <span>{t('Reporting period')}</span>
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
                  <div className="cx-s">{t('Project status · Shared by {name}', { name: project.publishedBy.name })}</div>
                </div>
              </div>
              <div className="cx-d">{dateRange(lang, r.periodStart, r.periodEnd)}</div>
              <div className="cx-d">{paddedDate(lang, r.createdOn)}</div>
              <div><span className="cx-st"><i />{t('Published')}</span></div>
              <button type="button" className="cx-btn cx-dl" onClick={() => window.print()}>
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
        <div className="cp-val" style={{ marginTop: 0, fontSize: 'var(--fs-12)' }}>
          {t('Published by {name} · {role}', { name: project.publishedBy.name, role: t(project.publishedBy.role) })}
        </div>
        <div className="cp-lbl">{t('Reporting period')}</div>
        <div className="cp-val" style={{ marginTop: 12 }}>{dateRange(lang, report.periodStart, report.periodEnd)}</div>
        <div className="cp-lbl">{t('Created on')}</div>
        <div className="cp-val" style={{ marginTop: 12 }}>{longDate(lang, report.createdOn)}</div>
        <div className="cp-lbl">{t('Published progress')}</div>
        <div className="cp-big">{report.progress}%</div>
        <div className="cp-lbl" style={{ marginTop: 14 }}>{t('Delivery summary')}</div>
        <div className="cp-val" style={{ marginTop: 12 }}>{report.summary}</div>
        <div className="cp-lbl">{t('Published forecast')}</div>
        <div className="cp-val" style={{ marginTop: 12 }}>{longDate(lang, report.forecast)}</div>
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
