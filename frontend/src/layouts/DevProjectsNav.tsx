import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useMyDashboard } from '@/features/tasks/myWorkApi';
import { usePrefs } from '@/shared/prefs/PrefsContext';

/** Developer sidebar group (Figma "Navigation / Borek Flow · Developer"): Projects plus the projects I am assigned to. */
export function DevProjectsNav() {
  const { t } = usePrefs();
  const [open, setOpen] = useState(true);
  const { data } = useMyDashboard();
  const projects = data?.projects ?? [];

  return (
    <div className="nav-group">
      <div className="nav-group-head">
        <NavLink to={paths.projects} end className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
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
