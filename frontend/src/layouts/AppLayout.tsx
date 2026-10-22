import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { navItems, paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import borekLogo from '@/assets/borek-logo-nav.svg';
import { ThemeToggle } from '@/shared/ui/ThemeToggle';
import { DevProjectsNav } from './DevProjectsNav';

export function AppLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { lang, setLang, t } = usePrefs();
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
        : pathname === paths.projects && user.role === 'developer'
          ? 'My Projects'
          :/^\/projects\/(?!new$)[^/]+(\/board)?\/?$/.test(pathname)
        ? 'Project Overview'
        : pathname.startsWith(`${paths.tasks}/`)
        ? 'Task details'
        : navItems.find((i) => pathname === i.to || pathname.startsWith(`${i.to}/`))?.label ?? 'Borek Flow';

  const items = navItems.filter((i) => i.roles.includes(user.role));

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <img src={borekLogo} alt="BOREK Solutions Group" width={112} height={26} />
          <span>Borek Flow</span>
        </div>
        <nav aria-label={t('Main')}>
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
              {t(item.label)}
            </NavLink>
          ))}
          {user.role === 'developer' && <DevProjectsNav />}
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-row">
            <h1 className="topbar-title">{t(title)}</h1>
            <div className="topbar-actions">
              <ThemeToggle />
              <div className="lang-switch" role="group" aria-label={t('Language')}>
                <button type="button" aria-pressed={lang === 'de'} onClick={() => setLang('de')}>DE</button>
                <i />
                <button type="button" aria-pressed={lang === 'en'} onClick={() => setLang('en')}>EN</button>
              </div>
              <i className="topbar-divider" />
              <Link to={paths.profile} className="user">
                <span className="avatar" aria-hidden="true">{initials}</span>
                <span className="user-name">{user.name}</span>
              </Link>
            </div>
          </div>
          <div className="splash" aria-hidden="true">
            <i /><i /><i /><i />
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
