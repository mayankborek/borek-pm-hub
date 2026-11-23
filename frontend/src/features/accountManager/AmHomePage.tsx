import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { dayMonth } from '@/features/client/format';
import { nextMilestone, useClientPortal } from '@/features/client/clientPortalApi';
import { HEALTH_LABEL } from '@/features/client/labels';
import { PortalPending } from '@/features/client/ui';
import { healthBadge } from './amUi';

/** Home (borek-flow-portal/index.html): four summary cards, the project list and upcoming milestones. */
export function AmHomePage() {
  const { user } = useAuth();
  const { t, lang } = usePrefs();
  const query = useClientPortal();
  const { data } = query;
  if (!data) return <PortalPending query={query} />;

  const { projects, today } = data;
  const firstName = user?.name.split(' ')[0] ?? '';
  const inReview = projects.reduce((n, p) => n + p.changeRequests.filter((c) => c.status === 'in_review').length, 0);
  const upcoming = projects
    .flatMap((p) => p.milestones.filter((m) => m.state !== 'done').map((m) => ({ p, m })))
    .sort((a, b) => a.m.dueDate.localeCompare(b.m.dueDate));
  const reports = projects.reduce((n, p) => n + p.reports.length, 0);

  return (
    <div className="am-page">
      <h1>{t('Welcome back, {name}', { name: firstName })}</h1>
      <p className="lead">{t('Project progress, upcoming milestones and your change requests.')}</p>

      <div className="grid4">
        <div className="card stat"><div className="label">{t('Active projects')}</div><div className="num">{projects.length}</div><div className="small">{t('Projects shared with you')}</div></div>
        <div className="card stat"><div className="label">{t('Requests in review')}</div><div className="num">{inReview}</div><div className="small">{t('Awaiting a decision')}</div></div>
        <div className="card stat"><div className="label">{t('Upcoming milestones')}</div><div className="num">{upcoming.length}</div><div className="small">{t('Across your projects')}</div></div>
        <div className="card stat"><div className="label">{t('Reports')}</div><div className="num">{reports}</div><div className="small">{t('Shared and generated reports')}</div></div>
      </div>

      <div className="home-grid">
        <section className="card">
          <h3>{t('Your projects')}</h3>
          <div className="small">{t('{n} projects available to you', { n: projects.length })}</div>
          <div className="row thead"><span>{t('Project')}</span><span>{t('Health')}</span><span>{t('Progress')}</span></div>
          {projects.map((p) => {
            const next = nextMilestone(p, today);
            return (
              <div className="row prow" key={p.id}>
                <div>
                  <Link className="t" to={paths.amProject(p.id)}>{p.name}</Link>
                  {next && <div className="meta">{next.name} · {dayMonth(lang, next.dueDate)}</div>}
                </div>
                <span><span className={healthBadge(p.health)}>{t(HEALTH_LABEL[p.health ?? 'none'])}</span></span>
                <div className="pg">
                  <div className="bar"><i style={{ width: `${p.progress}%` }} /></div>
                  <span>{p.progress}%</span>
                </div>
              </div>
            );
          })}
        </section>

        <section className="card">
          <h3>{t('Upcoming milestones')}</h3>
          <div style={{ marginTop: 14 }}>
            {upcoming.slice(0, 3).map(({ p, m }) => (
              <div className="ms" key={`${p.id}-${m.id}`}>
                <span className="d">{dayMonth(lang, m.dueDate)}</span>
                <div><b>{m.name}</b><small>{p.name}</small></div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
