import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import logo from '@/assets/borek-flow-portal-logo.svg';
import { initialsOf } from '@/features/client/format';
import './am.css';

const SETTINGS: string[] = [paths.amProfile, paths.amSecurity, paths.amNotifications, paths.amPreferences];

/** Top bar title per screen (borek-flow-portal): Home, Projects, a project's Overview, Profile. */
function titleFor(pathname: string) {
  if (pathname === paths.amHome) return 'Home';
  if (SETTINGS.includes(pathname)) return 'Profile';
  if (pathname === paths.amProjects) return 'Projects';
  if (/^\/account-manager\/projects\/[^/]+\/?$/.test(pathname)) return 'Overview';
  if (/^\/account-manager\/projects\/[^/]+\/reports\/[^/]+\/?$/.test(pathname)) return 'Report details';
  return 'Account Manager';
}

const SayContext = createContext<(message: string) => void>(() => undefined);
/** Shows a short toast, as the design does for actions that have no backend yet. */
export const useSay = () => useContext(SayContext);

function Toast({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState('');
  const [shown, setShown] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const say = useCallback((m: string) => {
    setMessage(m);
    setShown(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setShown(false), 1800);
  }, []);
  return (
    <SayContext.Provider value={say}>
      {children}
      <div className={shown ? 'toast show' : 'toast'} role="status">{message}</div>
    </SayContext.Provider>
  );
}

function Bell() {
  const say = useSay();
  const { t } = usePrefs();
  return (
    <button type="button" className="bell" aria-label={t('Notifications')} onClick={() => say(t('No new notifications'))}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
        <path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" />
      </svg>
    </button>
  );
}

/** Account Manager portal shell, built from borek-flow-portal: sidebar (Overview, Projects), top bar with bell and profile. */
export function AccountManagerLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { t } = usePrefs();
  if (!user) return null;
  // Profile and its settings pages have no sidebar.
  const settings = SETTINGS.includes(pathname);

  return (
    <div className="am">
      <Toast>
        <div className={settings ? 'shell no-side' : 'shell'}>
          {!settings && (
            <aside className="sidebar">
              <Link to={paths.amHome} aria-label={t('Borek Flow home')}>
                <img className="logo" src={logo} alt="BOREK Solutions Group" />
              </Link>
              <div className="sub">Borek Flow</div>
              <nav className="nav" aria-label={t('Main')}>
                <NavLink to={paths.amHome} end className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Overview')}</NavLink>
                <NavLink to={paths.amProjects} className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Projects')}</NavLink>
              </nav>
            </aside>
          )}
          <div className="main">
            <header className="topbar">
              <h2>{t(titleFor(pathname))}</h2>
              <div className="right">
                <Bell />
                <Link to={paths.amProfile} className="user">
                  <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>
                  {user.name}
                </Link>
              </div>
            </header>
            <main className="content" style={settings ? { maxWidth: 'none' } : undefined}>
              <Outlet />
            </main>
          </div>
        </div>
      </Toast>
    </div>
  );
}
