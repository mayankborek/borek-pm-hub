import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import amLogo from '@/assets/borek-flow-portal-logo.svg';
import { ThemeToggle } from '@/shared/ui/ThemeToggle';
import { initialsOf } from './format';
import { Notifications } from './Notifications';
import '@/features/accountManager/am.css';
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
  const { lang, setLang, t } = usePrefs();
  if (!user) return null;

  return (
    <div className="am">
      <div className="shell">
        <aside className="sidebar">
          <Link to={paths.clientHome} aria-label={t('Borek Flow home')}>
            <img className="logo" src={amLogo} alt="BOREK Solutions Group" />
          </Link>
          <div className="sub">Borek Flow</div>
          <nav className="nav" aria-label={t('Main')}>
            <NavLink to={paths.clientHome} end className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Home')}</NavLink>
            <NavLink to={paths.clientProjects} className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Projects')}</NavLink>
          </nav>
        </aside>
        <div className="main">
          <header className="topbar">
            <h2>{t(titleFor(pathname))}</h2>
            <div className="right">
              <span className="cp cp-tools">
                <Notifications />
              </span>
              <ThemeToggle />
              <div className="lang-switch" role="group" aria-label={t('Language')}>
                <button type="button" aria-pressed={lang === 'de'} onClick={() => setLang('de')}>DE</button>
                <i />
                <button type="button" aria-pressed={lang === 'en'} onClick={() => setLang('en')}>EN</button>
              </div>
              <Link to={paths.clientProfile} className="user">
                <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>
                {user.name}
              </Link>
            </div>
          </header>
          <main className="content">
            <div className="fit cp">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
