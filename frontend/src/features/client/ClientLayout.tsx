import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import borekLogo from '@/assets/borek-logo-nav.svg';
import borekLogoDark from '@/assets/borek-logo.png';
import { ThemeToggle } from '@/shared/ui/ThemeToggle';
import { initialsOf } from './format';
import { Notifications } from './Notifications';
import './clientPortal.css';

/** The design titles every project tab "Client Portal", except Overview and a single report. */
function titleFor(pathname: string) {
  if (pathname === paths.clientHome) return 'Home';
  if (pathname === paths.clientProfile) return 'Profile';
  if (pathname === paths.clientProjects) return 'Projects';
  if (/^\/client\/projects\/[^/]+\/?$/.test(pathname)) return 'Overview';
  if (/^\/client\/projects\/[^/]+\/reports\/[^/]+\/?$/.test(pathname)) return 'Report details';
  return 'Client Portal';
}

/** Client portal. Uses the same shell (sidebar, top bar, theme and language switches) as the staff app. */
export function ClientLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { lang, setLang, t, theme } = usePrefs();
  if (!user) return null;

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link className="brand" to={paths.clientHome} aria-label={t('Borek Flow home')}>
          <img src={theme === 'dark' ? borekLogoDark : borekLogo} alt="BOREK Solutions Group" width={112} height={26} />
          <span>Borek Flow</span>
        </Link>
        <nav aria-label={t('Main')}>
          <NavLink to={paths.clientHome} end className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            {t('Home')}
          </NavLink>
          <NavLink to={paths.clientProjects} className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            {t('Projects')}
          </NavLink>
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-row">
            <h1 className="topbar-title">{t(titleFor(pathname))}</h1>
            <div className="topbar-actions">
              <span className="cp cp-tools">
                <Notifications />
              </span>
              <ThemeToggle />
              <div className="lang-switch" role="group" aria-label={t('Language')}>
                <button type="button" aria-pressed={lang === 'de'} onClick={() => setLang('de')}>DE</button>
                <i />
                <button type="button" aria-pressed={lang === 'en'} onClick={() => setLang('en')}>EN</button>
              </div>
              <i className="topbar-divider" />
              <Link to={paths.clientProfile} className="user">
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
          <div className="fit cp">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
