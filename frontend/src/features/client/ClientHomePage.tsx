import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { dayMonth } from './format';
import { nextMilestone, useClientPortal } from './clientPortalApi';
import { CR_LABEL, HEALTH_LABEL, HEALTH_TONE } from './labels';
import { Badge, Bar, Kpi, PortalPending } from './ui';

export function ClientHomePage() {
  const { user } = useAuth();
  const { t, lang } = usePrefs();
  const query = useClientPortal();
  const { data } = query;
  if (!data) return <PortalPending query={query} />;

  const { projects, today } = data;
  const firstName = user?.name.split(' ')[0] ?? '';
  const upcoming = projects
    .flatMap((p) => p.milestones.filter((m) => m.state !== 'done' && m.dueDate >= today).map((m) => ({ p, m })))
    .sort((a, b) => a.m.dueDate.localeCompare(b.m.dueDate) || a.p.name.localeCompare(b.p.name));
  const requests = projects.flatMap((p) => p.changeRequests.map((c) => ({ p, c })));
  const inReview = requests.filter(({ c }) => c.status === 'in_review');
  const reports = projects.reduce((n, p) => n + p.reports.length, 0);

  return (
    <>
      <h2 className="cp-sec" style={{ marginTop: 24 }}>{t('Welcome back, {name}', { name: firstName })}</h2>
      <p className="cp-sub" style={{ marginTop: 6 }}>{t('Project progress, upcoming milestones and your change requests.')}</p>
      <div className="cp-grid4">
        <Kpi label={t('Active projects')} value={projects.length} hint={t('Projects shared with you')} />
        <Kpi label={t('Requests in review')} value={inReview.length} hint={t('Awaiting a decision')} />
        <Kpi label={t('Upcoming milestones')} value={upcoming.length} hint={t('Across your projects')} />
        <Kpi label={t('Reports')} value={reports} hint={t('Shared and generated reports')} />
      </div>
      <div className="cp-home-row">
        <div className="cp-card">
          <h4>{t('Your projects')}</h4>
          <p className="cp-small" style={{ marginTop: 12 }}>{t('{n} projects available to you', { n: projects.length })}</p>
          <div className="cp-tbl-h">
            <span>{t('Project')}</span>
            <span>{t('Health')}</span>
            <span>{t('Progress')}</span>
          </div>
          {projects.map((p) => {
            const next = nextMilestone(p, data.today);
            return (
              <div className="cp-tbl-r" key={p.id}>
                <div>
                  <Link to={paths.clientProject(p.id)}><b>{p.name}</b></Link>
                  {next && <div className="cp-m">{next.name} · {dayMonth(lang, next.dueDate)}</div>}
                </div>
                <div><Badge tone={HEALTH_TONE[p.health]}>{t(HEALTH_LABEL[p.health])}</Badge></div>
                <div className="cp-pg">
                  <Bar value={p.progress} style={{ width: 152 }} />
                  <span>{p.progress}%</span>
                </div>
              </div>
            );
          })}
        </div>
        <div className="cp-col">
          <div className="cp-card">
            <h4>{t('Upcoming milestones')}</h4>
            {upcoming.map(({ p, m }, i) => (
              <div className="cp-ms-row" key={`${p.id}-${m.id}`} style={i === 0 ? { marginTop: 24 } : undefined}>
                <span className="cp-dt">{dayMonth(lang, m.dueDate)}</span>
                <div><b>{m.name}</b><span>{p.name}</span></div>
              </div>
            ))}
          </div>
          <div className="cp-card">
            <h4>{t('Change requests')}</h4>
            {requests.map(({ p, c }) => (
              <div key={`${p.id}-${c.ref}`}>
                <div style={{ marginTop: 12, fontSize: 13 }}>
                  <Link to={paths.clientChangeRequests(p.id)}>{c.title}</Link>
                </div>
                <div className="cp-cr-line"><span>{p.name} · {c.ref}</span><em>{t(CR_LABEL[c.status])}</em></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
