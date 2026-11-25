import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { dayMonth, longDate } from '@/features/client/format';
import { nextMilestone, useClientPortal } from '@/features/client/clientPortalApi';
import { HEALTH_LABEL } from '@/features/client/labels';
import { Icon } from '@/features/client/icons';
import { PortalPending } from '@/features/client/ui';
import type { ClientProject } from '@/features/client/types';
import '@/features/client/clientScreens.css';

const isExternal = (p: ClientProject) => Boolean(p.organisation);

/** Account Manager dashboard (design.html): portfolio stats, projects at a glance, tasks needing attention and next actions. */
export function AmHomePage() {
  const { t, lang } = usePrefs();
  const query = useClientPortal();
  const { data } = query;
  if (!data) return <PortalPending query={query} />;

  const { projects, today, organisation } = data;
  const tasks = projects.flatMap((p) => (p.tasks ?? []).map((task) => ({ p, task })));
  const blocked = tasks.filter(({ task }) => task.status === 'Blocked');
  const overdue = tasks.filter(({ task }) => task.status !== 'Blocked' && task.dueDate && task.dueDate < today);
  const attention = [...blocked, ...overdue].slice(0, 2);
  const external = projects.filter(isExternal).length;
  const upcoming = projects
    .flatMap((p) => p.milestones.filter((m) => m.state !== 'done' && m.dueDate >= today).map((m) => ({ p, m })))
    .sort((a, b) => a.m.dueDate.localeCompare(b.m.dueDate))
    .slice(0, 2);

  return (
    <div className="cp">
      <section className="cx-welcome">
        <h1>{t('Your account portfolio')}</h1>
      </section>

      <section className="cx-stats" aria-label={t('Summary')}>
        <div className="cx-card cx-stat">
          <div className="cx-l">{t('Total projects')}</div>
          <Icon name="folder" className="cx-ico cx-stat-ico" />
          <div className="cx-n">{projects.length}</div>
          <div className="cx-s">{t('{a} external · {b} internal', { a: external, b: projects.length - external })}</div>
        </div>
        <div className="cx-card cx-stat">
          <div className="cx-l">{t('Active projects')}</div>
          <Icon name="layers" className="cx-ico cx-stat-ico cx-blue" strokeWidth={1.5} />
          <div className="cx-n">{projects.filter((p) => p.progress !== null).length}</div>
          <div className="cx-s">{t('Projects with published progress')}</div>
        </div>
        <div className="cx-card cx-stat">
          <div className="cx-l">{t('Blocked tasks')}</div>
          <Icon name="ban" className="cx-ico cx-stat-ico cx-orange" strokeWidth={1.5} />
          <div className="cx-n">{blocked.length}</div>
          <div className="cx-s">{blocked[0] ? blocked[0].task.title : t('Nothing blocked')}</div>
        </div>
        <div className="cx-card cx-stat">
          <div className="cx-l">{t('Overdue tasks')}</div>
          <Icon name="clock" className="cx-ico cx-stat-ico cx-red" />
          <div className="cx-n">{overdue.length}</div>
          <div className="cx-s">{t('Open tasks past due · {date}', { date: dayMonth(lang, today) })}</div>
        </div>
      </section>

      <div className="cx-sec">
        <h2>{t('Projects at a glance')}</h2>
        <Link to={paths.amProjects}>{t('View all projects')}</Link>
      </div>
      <section className="cx-proj-grid">
        {projects.map((p) => {
          const next = nextMilestone(p, today);
          return (
            <article className="cx-card cx-pcard" key={p.id}>
              <div className="cx-hd">
                <span className="cx-picon"><Icon name={isExternal(p) ? 'briefcase' : 'layers'} className="cx-ico cx-22" strokeWidth={1.6} /></span>
                <div>
                  <h3><Link to={paths.amProject(p.id)}>{p.name}</Link></h3>
                  <div className="cx-co">{p.organisation ?? organisation}</div>
                </div>
              </div>
              <div className="cx-tags">
                <span className="cx-tag">{t(isExternal(p) ? 'External' : 'Internal')}</span>
                <span className="cx-tag">{t(p.progress === null ? 'Planning' : 'Active')}</span>
                <span className={`cx-tag cx-${p.health ?? 'none'}`}>{t(HEALTH_LABEL[p.health ?? 'none'])}</span>
              </div>
              <div className="cx-prow"><span>{t('Task completion')}</span><b>{p.progress ?? '–'}{p.progress !== null && '%'}</b></div>
              <div className="cx-bar" role="progressbar" aria-valuenow={p.progress ?? undefined} aria-valuemin={0} aria-valuemax={100}>
                <i style={{ width: `${p.progress ?? 0}%` }} />
              </div>
              <p className="cx-note">{p.note ? t(p.note) : next ? t('Next milestone: {name}', { name: next.name }) : t('No eligible tasks planned yet')}</p>
              <p className="cx-due">{p.dueDate ? t('Due {date}', { date: longDate(lang, p.dueDate) }) : t('Dates to be planned')}</p>
            </article>
          );
        })}
      </section>

      <section className="cx-lower">
        <article className="cx-card cx-lcard">
          <div className="cx-hd"><h3>{t('Needs attention')}</h3></div>
          {attention.map(({ p, task }) => (
            <div className="cx-upd" key={`${p.id}-${task.id}`}>
              <div className="cx-t">{task.title}</div>
              <div className="cx-s">{t(task.status === 'Blocked' ? 'Blocked' : 'Overdue')} · {p.name} · {t('Due {date}', { date: dayMonth(lang, task.dueDate) })}</div>
            </div>
          ))}
          {!attention.length && <div className="cx-s">{t('Nothing needs attention')}</div>}
          <p className="cx-due"><Link to={paths.amProjects}>{t('Review task list')}</Link></p>
        </article>
        <article className="cx-card cx-lcard">
          <div className="cx-hd"><h3>{t('Your next actions')}</h3></div>
          {upcoming.map(({ p, m }) => (
            <div className="cx-upd" key={`${p.id}-${m.id}`}>
              <div className="cx-t">{m.name} · {dayMonth(lang, m.dueDate)}</div>
              <div className="cx-s">{p.name}</div>
            </div>
          ))}
          <p className="cx-due"><Link to={paths.amProjects}>{t('Open my task')}</Link></p>
        </article>
      </section>
    </div>
  );
}
