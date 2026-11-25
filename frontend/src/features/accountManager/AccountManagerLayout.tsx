import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import flowLogo from '@/assets/borek-flow-nav-white.svg';
import solutionsLogo from '@/assets/borek-solutions-nav-white.svg';
import { initialsOf } from '@/features/client/format';
import { Notifications } from '@/features/client/Notifications';
import './am.css';
import '@/features/client/clientPortal.css';
import '@/features/client/slateRounded.css';

const SETTINGS: string[] = [paths.amProfile, paths.amSecurity, paths.amNotifications, paths.amPreferences];

/** Top bar title per screen (borek-flow-portal): Home, Projects, a project's Overview, Profile. */
function titleFor(pathname: string) {
  if (pathname === paths.amHome) return 'Dashboard';
  if (SETTINGS.includes(pathname)) return 'Profile';
  if (pathname === paths.amProjects) return 'Projects';
  if (pathname === paths.amTasks) return 'Task List';
  if (/^\/account-manager\/projects\/[^/]+\/?$/.test(pathname)) return 'Overview';
  if (/^\/account-manager\/projects\/[^/]+\/backlog\/?$/.test(pathname)) return 'Backlog';
  if (/^\/account-manager\/projects\/[^/]+\/board\/?$/.test(pathname)) return 'Board';
  if (/^\/account-manager\/projects\/[^/]+\/change-requests\/?$/.test(pathname)) return 'Change Requests';
  if (/^\/account-manager\/projects\/[^/]+\/milestones\/?$/.test(pathname)) return 'Milestones';
  if (/^\/account-manager\/projects\/[^/]+\/reports\/[^/]+\/?$/.test(pathname)) return 'Report details';
  return 'Account Manager';
}

const SayContext = createContext<(message: string) => void>(() => undefined);
/** Shows a short toast, as the design does for actions that have no backend yet. */
export const useSay = () => useContext(SayContext);

export function Toast({ children }: { children: ReactNode }) {
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

/** Account Manager shell (design.html): sidebar (Dashboard, Task List, Projects), titled top bar with bell and profile. */
export function AccountManagerLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { t } = usePrefs();
  if (!user) return null;

  return (
    <div className="am am-slate am-client">
      <Toast>
        <div className="shell">
          <aside className="sidebar">
            <Link to={paths.amHome} aria-label={t('Borek Flow home')}>
              <img className="logo" src={flowLogo} alt="Borek Flow" />
            </Link>
            <nav className="nav" aria-label={t('Main')}>
              <NavLink to={paths.amHome} end className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Dashboard')}</NavLink>
              <NavLink to={paths.amTasks} className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Task List')}</NavLink>
              <NavLink to={paths.amProjects} className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Projects')}</NavLink>
            </nav>
            <img className="corp" src={solutionsLogo} alt="Borek Solutions Group" width={93} height={24} />
          </aside>
          <div className="main">
            <header className="topbar">
              <h2>{t(titleFor(pathname))}</h2>
              <div className="right">
                <span className="cp cp-tools">
                  <Notifications />
                </span>
                <Link to={paths.amProfile} className="user">
                  <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>
                  {user.name}
                </Link>
              </div>
            </header>
            <main className="content">
              <div className="fit">
                <Outlet />
              </div>
            </main>
          </div>
        </div>
      </Toast>
    </div>
  );
}
