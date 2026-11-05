import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import logo from '@/assets/borek-flow-logo.svg';
import { initialsOf } from './format';
import './clientPortal.css';

const bell = (
  <svg width="20" height="20" viewBox="1172 105 20 20" fill="none" aria-hidden="true">
    <path
      d="M1180.33 123.5H1183.67M1187 112.667C1187 111.341 1186.47 110.069 1185.54 109.131C1184.6 108.193 1183.33 107.667 1182 107.667C1180.67 107.667 1179.4 108.193 1178.46 109.131C1177.53 110.069 1177 111.341 1177 112.667C1177 118.5 1174.5 118.5 1174.5 120.167H1189.5C1189.5 118.5 1187 118.5 1187 112.667Z"
      stroke="#5C6178"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

/** The design titles every project tab "Client Portal", except Overview and a single report. */
function titleFor(pathname: string) {
  if (pathname === paths.clientHome) return 'Home';
  if (pathname === paths.clientProjects) return 'Projects';
  if (/^\/client\/projects\/[^/]+\/?$/.test(pathname)) return 'Overview';
  if (/^\/client\/projects\/[^/]+\/reports\/[^/]+\/?$/.test(pathname)) return 'Report details';
  return 'Client Portal';
}

export function ClientLayout() {
  const { user, signOut } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
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
            <button type="button" className="cp-bell" aria-label={t('Notifications')}>
              {bell}
            </button>
            <div className="cp-lang" role="group" aria-label={t('Language')}>
              <button type="button" className={lang === 'de' ? 'cp-on' : undefined} aria-pressed={lang === 'de'} onClick={() => setLang('de')}>
                DE
              </button>
              <button type="button" className={lang === 'en' ? 'cp-on' : undefined} aria-pressed={lang === 'en'} onClick={() => setLang('en')}>
                EN
              </button>
            </div>
            <div className="cp-user">
              <div className="cp-avatar" aria-hidden="true">
                {initialsOf(user.name)}
              </div>
              <span>{user.name}</span>
            </div>
            <button
              type="button"
              className="cp-signout"
              onClick={() => void signOut().then(() => navigate(paths.clientLogin, { replace: true }))}
            >
              {t('Sign out')}
            </button>
          </div>
        </header>
        <Outlet />
      </section>
    </div>
  );
}
