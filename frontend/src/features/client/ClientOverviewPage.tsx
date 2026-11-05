import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { dayMonth } from './format';
import { nextMilestone } from './clientPortalApi';
import { CR_LABEL, HEALTH_LABEL, HEALTH_TONE } from './labels';
import { useProjectContext } from './ClientProjectLayout';
import type { MilestoneState } from './types';
import { Badge, Bar, Kpi } from './ui';

const HEALTH_NOTE = {
  on_track: 'Progressing as planned',
  at_risk: 'Needs attention',
  off_track: 'Behind plan',
} as const;

const MILESTONE_BADGE: Record<MilestoneState, { label: string; tone?: 'late' | 'plan' }> = {
  done: { label: 'Done' },
  late: { label: 'Overdue', tone: 'late' },
  in_progress: { label: 'In progress', tone: 'plan' },
  planned: { label: 'Planned', tone: 'plan' },
};

const R = 87;
const CIRCUMFERENCE = 2 * Math.PI * R;

export function ClientOverviewPage() {
  const { project, today } = useProjectContext();
  const { t, lang } = usePrefs();

  const next = nextMilestone(project, today);
  const inReview = project.changeRequests.filter((c) => c.status === 'in_review').length;
  const total = project.changeRequests.length;
  const latestReport = [...project.reports].sort((a, b) => b.createdOn.localeCompare(a.createdOn))[0];

  return (
    <>
      <div className="cp-grid4" style={{ marginTop: 28 }}>
        <div className="cp-card cp-kpi cp-o">
          <div className="cp-l">{t('Project health')}</div>
          <div style={{ marginTop: 14 }}>
            <Badge tone={HEALTH_TONE[project.health]}>{t(HEALTH_LABEL[project.health])}</Badge>
          </div>
          <div className="cp-d" style={{ marginTop: 18 }}>{t(HEALTH_NOTE[project.health])}</div>
        </div>
        <Kpi overview label={t('Published progress')} value={`${project.progress}%`} hint={t('Latest shared delivery progress')} />
        <Kpi
          overview
          label={t('Next milestone')}
          value={next ? dayMonth(lang, next.dueDate) : '–'}
          hint={next ? `${next.name} · ${t(MILESTONE_BADGE[next.state].label)}` : t('Nothing planned')}
        />
        <Kpi overview label={t('Change requests')} value={total} hint={t('{n} in review', { n: inReview })} />
      </div>
      <div className="cp-ov2">
        <div className="cp-card" style={{ minHeight: 326 }}>
          <h4>{t('Delivery progress')}</h4>
          <p className="cp-sub" style={{ fontSize: 13, marginTop: 14 }}>{t('Latest published progress')}</p>
          <div className="cp-donut-wrap">
            <div className="cp-donut">
              <svg width="200" height="200" viewBox="0 0 200 200" aria-hidden="true">
                <circle cx="100" cy="100" r={R} fill="none" stroke="#F3F4F8" strokeWidth="26" />
                <circle
                  cx="100"
                  cy="100"
                  r={R}
                  fill="none"
                  stroke="#124F94"
                  strokeWidth="26"
                  strokeDasharray={`${(CIRCUMFERENCE * project.progress) / 100} ${CIRCUMFERENCE}`}
                  transform="rotate(-90 100 100)"
                />
              </svg>
              <div className="cp-c">
                <b>{project.progress}%</b>
                <span>{t('Complete')}</span>
              </div>
            </div>
            <div className="cp-legend">
              <div>{t('Complete')}<b>{project.progress}%</b></div>
              <div className="cp-r">{t('Remaining')}<b>{100 - project.progress}%</b></div>
            </div>
          </div>
        </div>
        <div className="cp-card">
          <h4>{t('Change requests')}</h4>
          <p className="cp-sub" style={{ fontSize: 13, marginTop: 14 }}>{t('{n} requests in total', { n: total })}</p>
          <div className="cp-crs">
            {(['in_review', 'approved', 'declined'] as const).map((status, i) => {
              const n = project.changeRequests.filter((c) => c.status === status).length;
              return (
                <div key={status}>
                  <div className="cp-row" style={i ? { marginTop: 18 } : undefined}>
                    <span>{t(CR_LABEL[status])}</span>
                    <b>{n}</b>
                  </div>
                  <Bar value={total ? (n / total) * 100 : 0} />
                </div>
              );
            })}
          </div>
        </div>
        <div className="cp-card" style={{ minHeight: 148, paddingBottom: 20 }}>
          <h4>{t('Milestones')}</h4>
          {project.milestones.map((m, i) => (
            <div className="cp-mrow" key={m.id} style={i === 0 ? { marginTop: 20 } : undefined}>
              <span className="cp-dt">{dayMonth(lang, m.dueDate)}</span>
              <span>{m.name}</span>
              <Badge tone={MILESTONE_BADGE[m.state].tone}>{t(MILESTONE_BADGE[m.state].label)}</Badge>
            </div>
          ))}
        </div>
        <div className="cp-card" style={{ minHeight: 148 }}>
          <h4>{t('Latest report')}</h4>
          {latestReport ? (
            <Link className="cp-link-b" to={paths.clientReport(project.id, latestReport.id)}>{latestReport.title}</Link>
          ) : (
            <p className="cp-sub">{t('No reports have been shared yet.')}</p>
          )}
        </div>
      </div>
    </>
  );
}
