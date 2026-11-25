import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { dayMonth } from '@/features/client/format';
import { nextMilestone } from '@/features/client/clientPortalApi';
import { useProjectContext } from '@/features/client/ClientProjectLayout';
import { CR_LABEL, HEALTH_LABEL, MILESTONE_BADGE } from '@/features/client/labels';
import type { ChangeRequestStatus } from '@/features/client/types';
import { milestoneBadge } from './amUi';
import { PRIORITIES, PRIORITY_COLOR, PRIORITY_LABEL, statusColor, statusNames } from './amWork';
import './amWork.css';

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
  const work = project.workItems ?? [];
  const open = work.filter((w) => !w.done);
  const dueSoon = open.filter((w) => w.dueDate && w.dueDate >= today && w.dueDate <= new Date(Date.parse(today) + 7 * 86_400_000).toISOString().slice(0, 10)).length;
  const byStatus = statusNames(open).map((s) => [s, open.filter((w) => w.status === s).length] as const);
  const byPriority = PRIORITIES.map((p) => [p, work.filter((w) => w.priority === p).length] as const);
  const maxStatus = Math.max(1, ...byStatus.map(([, n]) => n));
  const maxPriority = Math.max(1, ...byPriority.map(([, n]) => n));
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

      <div className="grid4">
        <div className="card stat sm"><div className="label">{t('Open tasks')}</div><div className="num">{open.length}</div><div className="small">{t('{n} due this week', { n: dueSoon })}</div></div>
        <div className="card stat sm"><div className="label">{t('Completed')}</div><div className="num">{work.length - open.length}</div><div className="small">{t('{a} of {b} tasks complete', { a: work.length - open.length, b: work.length })}</div></div>
        <div className="card stat sm"><div className="label">{t('Team members')}</div><div className="num">{project.teamSize ?? 0}</div></div>
      </div>

      <div className="grid2">
        <section className="card">
          <h3>{t('Tasks by status')}</h3>
          <div className="small">{t('{n} active tasks', { n: open.length })}</div>
          {byStatus.map(([s, n]) => (
            <div className="ov-row" key={s}>
              <span>{t(s)}</span>
              <div className="bar"><i style={{ width: `${(n / maxStatus) * 100}%`, background: statusColor(s) }} /></div>
              <b>{n}</b>
            </div>
          ))}
        </section>
        <section className="card">
          <h3>{t('Tasks by priority')}</h3>
          <div className="small">{t('How the {n} tasks of this project are prioritized.', { n: work.length })}</div>
          <div className="ov-cols">
            {byPriority.map(([p, n]) => (
              <div key={p}>
                <b>{n}</b>
                <i style={{ height: `${(n / maxPriority) * 120}px`, background: PRIORITY_COLOR[p] }} />
                <span>{t(PRIORITY_LABEL[p])}</span>
              </div>
            ))}
          </div>
        </section>
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
