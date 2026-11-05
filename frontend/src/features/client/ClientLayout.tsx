import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import logo from '@/assets/borek-flow-logo.svg';
import { initialsOf } from './format';
import { Notifications } from './Notifications';
import './clientPortal.css';

/** The design titles every project tab "Client Portal", except Overview and a single report. */
function titleFor(pathname: string) {
  if (pathname === paths.clientHome) return 'Home';
  if (pathname === paths.clientProjects) return 'Projects';
  if (/^\/client\/projects\/[^/]+\/?$/.test(pathname)) return 'Overview';
  if (/^\/client\/projects\/[^/]+\/reports\/[^/]+\/?$/.test(pathname)) return 'Report details';
  return 'Client Portal';
}

export function ClientLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { lang, setLang, t } = usePrefs();
  if (!user) return null;

  return (
    <div className="cp">
      <aside className="cp-side">
        <Link to={paths.clientHome} aria-label={t('Borek Flow home')}>
          <img className="cp-logo" src={logo} alt="Borek Solutions Group – Borek Flow" />
        </Link>
        <nav className="cp-nav" aria-label={t('Main')}>
          <NavLink to={paths.clientHome} end className={({ isActive }) => (isActive ? 'cp-active' : undefined)}>
            {t('Home')}
          </NavLink>
          <NavLink to={paths.clientProjects} className={({ isActive }) => (isActive ? 'cp-active' : undefined)}>
            {t('Projects')}
          </NavLink>
        </nav>
      </aside>
      <section className="cp-main">
        <header className="cp-top">
          <h1>{t(titleFor(pathname))}</h1>
          <div className="cp-tools">
            <Notifications />
            <div className="cp-lang" role="group" aria-label={t('Language')}>
              <button type="button" className={lang === 'de' ? 'cp-on' : undefined} aria-pressed={lang === 'de'} onClick={() => setLang('de')}>
                DE
              </button>
              <button type="button" className={lang === 'en' ? 'cp-on' : undefined} aria-pressed={lang === 'en'} onClick={() => setLang('en')}>
                EN
              </button>
            </div>
            <Link className="cp-user" to={paths.clientProfile}>
              <div className="cp-avatar" aria-hidden="true">
                {initialsOf(user.name)}
              </div>
              <span>{user.name}</span>
            </Link>
          </div>
        </header>
        <Outlet />
      </section>
    </div>
  );
}
