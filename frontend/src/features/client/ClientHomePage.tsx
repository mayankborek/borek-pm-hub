import { Link } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthContext';
import { usePortalPaths } from './portalPaths';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { dayMonth, longDate, paddedDate, pct } from './format';
import { nextMilestone, useClientPortal } from './clientPortalApi';
import { HEALTH_LABEL } from './labels';
import { Icon } from './icons';
import { PortalPending } from './ui';
import './clientScreens.css';

const WINDOW_DAYS = 14;
const addDays = (iso: string, n: number) => new Date(Date.parse(`${iso}T00:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);

export function ClientHomePage() {
  const pp = usePortalPaths();
  const { user } = useAuth();
  const { t, lang } = usePrefs();
  const query = useClientPortal();
  const { data } = query;
  if (!data) return <PortalPending query={query} />;

  const { projects, today, updates, organisation } = data;
  const firstName = user?.name.split(' ')[0] ?? '';
  const upcoming = projects
    .flatMap((p) => p.milestones.filter((m) => m.state !== 'done' && m.dueDate >= today).map((m) => ({ p, m })))
    .sort((a, b) => a.m.dueDate.localeCompare(b.m.dueDate) || a.p.name.localeCompare(b.p.name));
  const soon = upcoming.filter(({ m }) => m.dueDate <= addDays(today, WINDOW_DAYS));
  const awaiting = projects.reduce((n, p) => n + p.clientActions, 0);
  const reports = projects.flatMap((p) => p.reports.map((r) => ({ p, r })));
  const latest = [...reports].sort((a, b) => b.r.publishedAt.localeCompare(a.r.publishedAt))[0];

  return (
    <>
      <section className="cx-welcome">
        <h1>{t('Welcome back, {name}', { name: firstName })}</h1>
        <p>{organisation} · {t('Your client workspace')}</p>
      </section>

      <section className="cx-stats" aria-label={t('Summary')}>
        <div className="cx-card cx-stat">
          <div className="cx-l">{t('Active projects')}</div>
          <Icon name="folder" className="cx-ico cx-stat-ico" />
          <div className="cx-n">{projects.length}</div>
          <div className="cx-s">{t('Currently in delivery')}</div>
        </div>
        <div className="cx-card cx-stat">
          <div className="cx-l">{t('Awaiting your input')}</div>
          <Icon name="layers" className="cx-ico cx-stat-ico cx-blue" strokeWidth={1.5} />
          <div className="cx-n">{awaiting}</div>
          <div className="cx-s">{awaiting ? t('{n} items need your input', { n: awaiting }) : t('No input needed from you')}</div>
        </div>
        <div className="cx-card cx-stat">
          <div className="cx-l">{t('Upcoming milestones')}</div>
          <Icon name="ban" className="cx-ico cx-stat-ico cx-orange" strokeWidth={1.5} />
          <div className="cx-n">{soon.length}</div>
          <div className="cx-s">{t('Next {n} days', { n: WINDOW_DAYS })}</div>
        </div>
        <div className="cx-card cx-stat">
          <div className="cx-l">{t('Shared reports')}</div>
          <Icon name="clock" className="cx-ico cx-stat-ico" />
          <div className="cx-n">{reports.length}</div>
          <div className="cx-s">{t('Published reports available')}</div>
        </div>
      </section>

      <section className="cx-card cx-latest" aria-labelledby="cx-latest-h">
        <h2 id="cx-latest-h">{t('Latest report')}</h2>
        {latest ? (
          <>
            <span className="cx-pub">{t('Published · {date}', { date: paddedDate(lang, latest.r.publishedAt.slice(0, 10)) })}</span>
            <div className="cx-t">{latest.r.title}</div>
            <div className="cx-m">{t('{name} · Shared by your Project Manager', { name: latest.p.name })}</div>
            <Link className="cx-btn" to={pp.reports(latest.p.id)}>
              {t('View reports')} <Icon name="arrow" />
            </Link>
          </>
        ) : (
          <div className="cx-m" style={{ marginTop: 20 }}>{t('No reports have been shared yet')}</div>
        )}
      </section>

      <div className="cx-sec">
        <h2>{t('My projects')}</h2>
        <Link to={pp.projects}>{t('View all projects')}</Link>
      </div>
      <section className="cx-proj-grid">
        {projects.map((p) => {
          const next = nextMilestone(p, today);
          return (
            <article className="cx-card cx-pcard" key={p.id}>
              <div className="cx-hd">
                <span className="cx-picon"><Icon name="briefcase" className="cx-ico cx-22" strokeWidth={1.6} /></span>
                <div>
                  <h3><Link to={pp.project(p.id)}>{p.name}</Link></h3>
                  <div className="cx-co">{organisation}</div>
                </div>
              </div>
              <div className="cx-tags">
                <span className="cx-tag">{t('Active')}</span>
                <span className={`cx-tag cx-${p.health ?? 'none'}`}>{t(HEALTH_LABEL[p.health ?? 'none'])}</span>
              </div>
              <div className="cx-prow"><span>{t('Published progress')}</span><b>{pct(p.progress)}</b></div>
              <div className="cx-bar" role="progressbar" aria-valuenow={p.progress ?? undefined} aria-valuemin={0} aria-valuemax={100}>
                <i style={{ width: `${p.progress ?? 0}%` }} />
              </div>
              <p className="cx-note">{p.note ? t(p.note) : next ? t('Next milestone: {name}', { name: next.name }) : t('Nothing planned')}</p>
              <p className="cx-due">{t('Due {date}', { date: longDate(lang, p.dueDate) })}</p>
            </article>
          );
        })}
      </section>

      <section className="cx-lower">
        <article className="cx-card cx-lcard">
          <div className="cx-hd">
            <h3>{t('Upcoming milestones')}</h3>
            {projects[0] && (
              <Link to={pp.milestones(projects[0].id)}>
                {t('View all')} <Icon name="arrow" className="cx-ico cx-11" strokeWidth={2} />
              </Link>
            )}
          </div>
          {upcoming.slice(0, 3).map(({ p, m }) => (
            <div className="cx-ms" key={`${p.id}-${m.id}`}>
              <span className="cx-d">{dayMonth(lang, m.dueDate)}</span>
              <div><div className="cx-t">{m.name}</div><div className="cx-s">{p.name}</div></div>
            </div>
          ))}
        </article>
        <article className="cx-card cx-lcard">
          <div className="cx-hd"><h3>{t('Recent updates')}</h3></div>
          {updates.slice(0, 3).map((u) => (
            <div className="cx-upd" key={u.id}>
              <div className="cx-t">{t(u.title)}</div>
              <div className="cx-s">{u.meta}</div>
            </div>
          ))}
        </article>
      </section>
    </>
  );
}
