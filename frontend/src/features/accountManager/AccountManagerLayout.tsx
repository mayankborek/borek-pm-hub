import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import borekLogo from '@/assets/borek-logo-nav.svg';
import borekLogoDark from '@/assets/borek-logo.png';
import { ThemeToggle } from '@/shared/ui/ThemeToggle';
import { initialsOf } from '@/features/client/format';
import '@/features/client/clientPortal.css';
import '@/features/admin/admin.css';

/** Top bar title per screen (borek-flow): Overview and a single report are named, other project tabs say "Account Manager". */
function titleFor(pathname: string) {
  if (pathname === paths.amHome) return 'Overview';
  if (pathname === paths.amProfile) return 'Profile';
  if (pathname === paths.amProjects) return 'Projects';
  if (/^\/account-manager\/projects\/[^/]+\/?$/.test(pathname)) return 'Overview';
  if (/^\/account-manager\/projects\/[^/]+\/reports\/[^/]+\/?$/.test(pathname)) return 'Report details';
  return 'Account Manager';
}

/** Account Manager portal. Same shell (sidebar, top bar, theme and language switches) as the client and admin views. */
export function AccountManagerLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { lang, setLang, t, theme } = usePrefs();
  if (!user) return null;

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link className="brand" to={paths.amHome} aria-label={t('Borek Flow home')}>
          <img src={theme === 'dark' ? borekLogoDark : borekLogo} alt="BOREK Solutions Group" width={112} height={26} />
          <span>Borek Flow</span>
        </Link>
        <nav aria-label={t('Main')}>
          <NavLink to={paths.amHome} end className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            {t('Overview')}
          </NavLink>
          <NavLink to={paths.amProjects} className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            {t('Projects')}
          </NavLink>
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-row">
            <h1 className="topbar-title">{t(titleFor(pathname))}</h1>
            <div className="topbar-actions">
              <ThemeToggle />
              <div className="lang-switch" role="group" aria-label={t('Language')}>
                <button type="button" aria-pressed={lang === 'de'} onClick={() => setLang('de')}>DE</button>
                <i />
                <button type="button" aria-pressed={lang === 'en'} onClick={() => setLang('en')}>EN</button>
              </div>
              <i className="topbar-divider" />
              <Link to={paths.amProfile} className="user">
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
