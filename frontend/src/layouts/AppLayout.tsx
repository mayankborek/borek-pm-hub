import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { navItems, paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import flowLogo from '@/assets/borek-flow-nav-white.svg';
import solutionsLogo from '@/assets/borek-solutions-nav-white.svg';
import { DevProjectsNav } from './DevProjectsNav';
import './pmShell.css';

export function AppLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { t } = usePrefs();
  if (!user) return null;

  const initials = user.name
    .split(' ')
    .map((p) => p.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase();
  const title =
    pathname === paths.profile
      ? 'Profile'
      : pathname === paths.myWork
        ? 'My Work'
        : pathname === paths.projectNew
          ? 'Create Project'
          : pathname === paths.projects && user.role === 'developer'
          ? 'My Projects'
          : /^\/projects\/(?!new$)[^/]+\/board\/?$/.test(pathname)
        ? 'Board'
        : /^\/projects\/(?!new$)[^/]+\/list\/?$/.test(pathname)
        ? 'Backlog'
        : /^\/projects\/[^/]+\/milestones\/?$/.test(pathname)
        ? 'Milestones'
        : /^\/projects\/[^/]+\/settings(\/|$)/.test(pathname)
        ? 'Settings'
        : /^\/projects\/[^/]+\/requirements\/?$/.test(pathname)
        ? 'Requirements'
        : /^\/projects\/[^/]+\/change-requests\/?$/.test(pathname)
        ? 'Change Requests'
        : /^\/projects\/(?!new$)[^/]+\/?$/.test(pathname)
        ? 'Overview'
        : pathname.startsWith(`${paths.tasks}/`)
        ? 'Task details'
        : navItems.find((i) => pathname === i.to || pathname.startsWith(`${i.to}/`))?.label ?? 'Borek Flow';

  const items = navItems.filter((i) => i.roles.includes(user.role));

  return (
    <div className="shell pm">
      <aside className="sidebar">
        <Link to={paths.dashboard} className="brand" aria-label="Borek Flow">
          <img src={flowLogo} alt="Borek Flow" width={130} height={35} />
        </Link>
        <nav aria-label={t('Main')}>
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
              {t(item.label)}
            </NavLink>
          ))}
          {user.role === 'developer' && <DevProjectsNav />}
        </nav>
        <img className="corp" src={solutionsLogo} alt="Borek Solutions Group" width={93} height={24} />
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-row">
            <h1 className="topbar-title">{t(title)}</h1>
            <div className="topbar-actions">
              <span className="bell" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
                  <path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" />
                </svg>
              </span>
              <span className="topbar-divider" aria-hidden="true" />
              <Link to={paths.profile} className="user">
                <span className="avatar" aria-hidden="true">{initials}</span>
                <span className="user-name">{user.name}</span>
              </Link>
            </div>
          </div>
        </header>
        <main className="content">
          <div className="fit">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
