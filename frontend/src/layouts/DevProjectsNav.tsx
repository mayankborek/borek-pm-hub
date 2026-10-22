import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useMyDashboard } from '@/features/tasks/myWorkApi';
import { usePrefs } from '@/shared/prefs/PrefsContext';

/** Developer sidebar group (Figma "Navigation / Borek Flow · Developer"): Projects plus the projects I am assigned to. */
export function DevProjectsNav() {
  const { t } = usePrefs();
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  // Task details sit under Projects in the Figma navigation, so the group stays highlighted there.
  const onTask = pathname.startsWith(`${paths.tasks}/`);
  const { data } = useMyDashboard();
  const projects = data?.projects ?? [];

  return (
    <div className="nav-group">
      <div className="nav-group-head">
        <NavLink to={paths.projects} end onClick={() => setOpen((o) => !o)} className={({ isActive }) => (isActive || onTask ? 'nav-link active' : 'nav-link')}>
          {t('Projects')}
        </NavLink>
        <button
          type="button"
          className="nav-chevron"
          aria-expanded={open}
          aria-label={open ? t('Collapse projects') : t('Expand projects')}
          onClick={() => setOpen(!open)}
        >
          {open ? '⌄' : '›'}
        </button>
      </div>
      {open &&
        (projects.length === 0 ? (
          data && <p className="nav-note">{t('No assigned projects')}</p>
        ) : (
          <ul className="nav-sub">
            {projects.map((p) => (
              <li key={p.id}>
                <NavLink to={paths.project(p.id)} className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  {p.name}
                </NavLink>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
