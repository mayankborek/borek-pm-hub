import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import borekLogo from '@/assets/borek-logo-nav.svg';
import borekLogoDark from '@/assets/borek-logo.png';
import { ThemeToggle } from '@/shared/ui/ThemeToggle';
import { initialsOf } from '@/features/client/format';
import '@/features/client/clientPortal.css';
import './admin.css';

const TITLES: Record<string, string> = {
  [paths.adminUsers]: 'Users',
  [paths.adminOrganisations]: 'Client organisations',
  [paths.adminRoles]: 'Role access',
  [paths.adminProfile]: 'Profile',
};

const NAV = [
  { to: paths.adminUsers, label: 'Users' },
  { to: paths.adminOrganisations, label: 'Client organisations' },
  { to: paths.adminRoles, label: 'Role access' },
];

/** Admin console. Uses the same shell (sidebar, top bar, theme and language switches) as the staff app. */
export function AdminLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { lang, setLang, t, theme } = usePrefs();
  const section = `/${pathname.split('/').slice(1, 3).join('/')}`;
  if (!user) return null;

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link className="brand" to={paths.adminUsers} aria-label={t('Borek Flow home')}>
          <img src={theme === 'dark' ? borekLogoDark : borekLogo} alt="BOREK Solutions Group" width={112} height={26} />
          <span>Borek Flow</span>
        </Link>
        <nav aria-label={t('Admin')}>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
              {t(n.label)}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-row">
            <h1 className="topbar-title">{t(TITLES[section] ?? 'Users')}</h1>
            <div className="topbar-actions">
              <ThemeToggle />
              <div className="lang-switch" role="group" aria-label={t('Language')}>
                <button type="button" aria-pressed={lang === 'de'} onClick={() => setLang('de')}>DE</button>
                <i />
                <button type="button" aria-pressed={lang === 'en'} onClick={() => setLang('en')}>EN</button>
              </div>
              <i className="topbar-divider" />
              <Link to={paths.adminProfile} className="user">
                <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>
                <span className="user-name">{user.name}</span>
              </Link>
            </div>
          </div>
          <div className="splash" aria-hidden="true">
            <i /><i /><i /><i />
          </div>
        </header>
        <main className="content">
          <div className="fit cp ad">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
