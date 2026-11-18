import { useState } from 'react';
import { Link } from 'react-router-dom';
import { usePortalPaths } from './portalPaths';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { longDate } from './format';
import { nextMilestone, useClientPortal } from './clientPortalApi';
import { HEALTH_LABEL } from './labels';
import { Icon } from './icons';
import { EmptyCard, PortalPending } from './ui';
import './clientScreens.css';

type Filter = 'all' | 'active' | 'completed';

export function ClientProjectsPage() {
  const pp = usePortalPaths();
  const { t, lang } = usePrefs();
  const query = useClientPortal();
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const { data } = query;
  if (!data) return <PortalPending query={query} />;

  const { projects, today } = data;
  if (!projects.length) return <EmptyCard />;

  const completed = (p: (typeof projects)[number]) => p.progress >= 100;
  const counts = { all: projects.length, active: projects.filter((p) => !completed(p)).length, completed: projects.filter(completed).length };
  const q = search.trim().toLowerCase();
  const shown = projects
    .filter((p) => filter === 'all' || (filter === 'completed') === completed(p))
    .filter((p) => !q || p.name.toLowerCase().includes(q) || p.code.toLowerCase().includes(q));
  const chips: [Filter, string][] = [
    ['all', 'All projects'],
    ['active', 'Active'],
    ['completed', 'Completed'],
  ];

  return (
    <>
      <section className="cx-ph">
        <div>
          <h1>{t('Your projects')}</h1>
          <p>{t('View and track all your projects with Borek.')}</p>
        </div>
        <span className="cx-badge">{t('{n} active projects', { n: counts.active })}</span>
      </section>

      <div className="cx-filters">
        {chips.map(([key, label]) => (
          <button key={key} type="button" className="cx-chip" aria-pressed={filter === key} onClick={() => setFilter(key)}>
            {t(label)} · {counts[key]}
          </button>
        ))}
        <label className="cx-search">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('Search projects by name or ID…')}
            aria-label={t('Search projects')}
          />
        </label>
      </div>

      <section className="cx-plist">
        {shown.map((p) => {
          const next = nextMilestone(p, today);
          return (
            <article className="cx-card cx-pr" key={p.id}>
              <div className="cx-hd">
                <span className="cx-picon"><Icon name="briefcase" className="cx-ico cx-22" strokeWidth={1.6} /></span>
                <div>
                  <h3>{p.name}</h3>
                  <div className="cx-id">{p.code} · {p.category}</div>
                </div>
              </div>
              <span className={`cx-status cx-${p.health}`}>{t(HEALTH_LABEL[p.health])}</span>
              <div className="cx-meta">
                <div><div className="cx-k">{t('Project Manager')}</div><div className="cx-v">{p.publishedBy.name}</div></div>
                <div><div className="cx-k">{t('Next milestone')}</div><div className="cx-v">{next ? next.name : '–'}</div></div>
                <div><div className="cx-k">{t('Target completion')}</div><div className="cx-v">{longDate(lang, p.dueDate)}</div></div>
                <div className="cx-pg">
                  <div className="cx-k"><span>{t('Project progress')}</span><b>{p.progress}%</b></div>
                  <div className="cx-bar" role="progressbar" aria-valuenow={p.progress} aria-valuemin={0} aria-valuemax={100}>
                    <i style={{ width: `${p.progress}%` }} />
                  </div>
                </div>
              </div>
              <hr />
              <div className="cx-ft">
                <span>{t('Start date: {date}', { date: longDate(lang, p.startDate) })}</span>
                <Link className="cx-btn" to={pp.project(p.id)}>
                  {t('View project')} <Icon name="arrow" />
                </Link>
              </div>
            </article>
          );
        })}
        {!shown.length && <p className="cx-none">{t('No projects match your search.')}</p>}
      </section>
    </>
  );
}
