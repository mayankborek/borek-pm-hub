import { Link, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { dateRange, longDate } from './format';
import { useProjectContext } from './ClientProjectLayout';
import { EmptyCard } from './ui';

const downloadIcon = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
    <path d="M7 1.5v8M10 6.5l-3 3-3-3M2 10.5v2h10v-2" stroke="#124F94" strokeWidth="1.4" />
  </svg>
);
const backIcon = (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <path d="M10.5 6H1.5M5 2.5L1.5 6 5 9.5" stroke="#124F94" strokeWidth="1.4" />
  </svg>
);

export function ClientReportsPage() {
  const { project } = useProjectContext();
  const { t, lang } = usePrefs();

  return (
    <>
      <h2 className="cp-sec" style={{ fontSize: 20, marginTop: 32 }}>{t('Reports')}</h2>
      <p className="cp-sub" style={{ marginTop: 10 }}>{t('View published reports shared with your organisation.')}</p>
      {!project.reports.length && <EmptyCard />}
      {project.reports.length > 0 && (
      <div className="cp-rt">
        <div className="cp-h">
          <span>{t('Report')}</span>
          <span>{t('Reporting period')}</span>
          <span>{t('Created on')}</span>
          <span>{t('Status')}</span>
          <span />
        </div>
        {project.reports.map((r) => (
          <div className="cp-r" key={r.id}>
            <Link to={paths.clientReport(project.id, r.id)}><b>{r.title}</b></Link>
            <span>{dateRange(lang, r.periodStart, r.periodEnd)}</span>
            <span>{longDate(lang, r.createdOn)}</span>
            <span className="cp-pub">{t('Published')}</span>
            <button type="button" className="cp-dl" onClick={() => window.print()}>
              {downloadIcon}
              {t('Download')}
            </button>
          </div>
        ))}
      </div>
      )}
      <p className="cp-small" style={{ marginTop: 16 }}>
        {t('Reports include only published information shared with your organisation.')}
      </p>
    </>
  );
}

export function ClientReportPage() {
  const { reportId } = useParams();
  const { project } = useProjectContext();
  const { t, lang } = usePrefs();
  const report = project.reports.find((r) => r.id === reportId);

  if (!report) {
    return (
      <EmptyCard
        title="Report not found"
        text="This report does not exist or has not been shared with you."
        action={<Link to={paths.clientReports(project.id)}>{t('Back')}</Link>}
      />
    );
  }

  return (
    <div className="cp-rd">
      <Link className="cp-back" to={paths.clientReports(project.id)}>
        {backIcon}
        {t('Back')}
      </Link>
      <h2>{report.title}</h2>
      <div className="cp-card">
        <div className="cp-val" style={{ marginTop: 0, fontSize: 12 }}>
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
