import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { dayMonth } from '@/features/client/format';
import { nextMilestone } from '@/features/client/clientPortalApi';
import { useProjectContext } from '@/features/client/ClientProjectLayout';
import { CR_LABEL, HEALTH_LABEL, MILESTONE_BADGE } from '@/features/client/labels';
import type { ChangeRequestStatus } from '@/features/client/types';
import { milestoneBadge } from './amUi';

const R = 76;
const C = 2 * Math.PI * R;
const CR_ORDER: ChangeRequestStatus[] = ['in_review', 'approved', 'declined'];

/** Project overview (borek-flow-portal/project.html): health, progress, change requests, milestones, latest report. */
export function AmOverviewPage() {
  const { project, today } = useProjectContext();
  const { t, lang } = usePrefs();
  const progress = project.progress ?? 0;
  const next = nextMilestone(project, today);
  const crs = project.changeRequests;
  const inReview = crs.filter((c) => c.status === 'in_review').length;
  const latest = [...project.reports].sort((a, b) => b.publishedAt.localeCompare(a.publishedAt))[0];

  return (
    <>
      <div className="grid4" style={{ marginTop: 20 }}>
        <div className="card stat sm"><div className="label">{t('Project health')}</div><div className="num blue">{t(HEALTH_LABEL[project.health ?? 'none'])}</div><div className="small">{t('Progressing as planned')}</div></div>
        <div className="card stat sm"><div className="label">{t('Published progress')}</div><div className="num">{progress}%</div><div className="small">{t('Latest shared delivery progress')}</div></div>
        <div className="card stat sm">
          <div className="label">{t('Next milestone')}</div>
          <div className="num">{next ? dayMonth(lang, next.dueDate) : '–'}</div>
          <div className="small">{next ? `${next.name} · ${t(MILESTONE_BADGE[next.state].label)}` : t('Nothing planned')}</div>
        </div>
        <div className="card stat sm"><div className="label">{t('Change requests')}</div><div className="num">{crs.length}</div><div className="small">{t('{n} in review', { n: inReview })}</div></div>
      </div>

      <div className="grid2">
        <section className="card">
          <h3>{t('Delivery progress')}</h3>
          <div className="small">{t('Latest published progress')}</div>
          <div className="donutwrap">
            <div className="donut">
              <svg width="180" height="180" viewBox="0 0 180 180" aria-hidden="true">
                <circle cx="90" cy="90" r={R} fill="none" stroke="var(--bg)" strokeWidth="22" />
                <circle cx="90" cy="90" r={R} fill="none" stroke="var(--blue)" strokeWidth="22" strokeDasharray={C} strokeDashoffset={C * (1 - progress / 100)} />
              </svg>
              <div className="c"><b>{progress}%</b><span>{t('Complete')}</span></div>
            </div>
            <div className="legend">
              <div><i />{t('Complete')}<b>{progress}%</b></div>
              <div><i className="r" />{t('Remaining')}<b>{100 - progress}%</b></div>
            </div>
          </div>
        </section>

        <section className="card">
          <h3>{t('Change requests')}</h3>
          <div className="small">{t('{n} requests in total', { n: crs.length })}</div>
          {CR_ORDER.map((status) => {
            const n = crs.filter((c) => c.status === status).length;
            return (
              <div className="cr" key={status}>
                <div className="h"><span>{t(CR_LABEL[status])}</span><b>{n}</b></div>
                <div className="bar">{n > 0 && <i style={{ width: `${(n / crs.length) * 100}%` }} />}</div>
              </div>
            );
          })}
        </section>
      </div>

      <div className="grid2">
        <section className="card">
          <h3>{t('Milestones')}</h3>
          <div style={{ marginTop: 14 }}>
            {project.milestones.filter((m) => m.state !== 'done').map((m) => (
              <div className="mrow" key={m.id}>
                <span className="d">{dayMonth(lang, m.dueDate)}</span>
                <span>{m.name}</span>
                <span className={milestoneBadge(m.state)}>{t(MILESTONE_BADGE[m.state].label)}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="card">
          <h3>{t('Latest report')}</h3>
          {latest ? (
            <Link className="report" to={paths.amReport(project.id, latest.id)}>{latest.title}</Link>
          ) : (
            <p className="small">{t('No reports have been shared yet.')}</p>
          )}
        </section>
      </div>
    </>
  );
}
