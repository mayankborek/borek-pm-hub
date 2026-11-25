import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import flowLogo from '@/assets/borek-flow-nav-white.svg';
import solutionsLogo from '@/assets/borek-solutions-nav-white.svg';
import { Notifications } from './Notifications';
import { UserMenu } from './UserMenu';
import { Toast } from '@/features/accountManager/AccountManagerLayout';
import '@/features/accountManager/am.css';
import './clientPortal.css';
import './slateRounded.css';

/** The design titles every project tab "Client Portal", except Overview and a single report. */
function titleFor(pathname: string) {
  if (pathname === paths.clientHome) return 'Dashboard';
  if (pathname.startsWith(paths.clientProfile)) return 'Profile';
  if (pathname === paths.clientProjects) return 'Projects';
  if (/^\/client\/projects\/[^/]+\/?$/.test(pathname)) return 'Overview';
  if (/^\/client\/projects\/[^/]+\/reports\/[^/]+\/?$/.test(pathname)) return 'Report details';
  return 'Client Portal';
}

/** Client portal. Uses the same shell (sidebar, top bar, theme and language switches) as the staff app. */
export function ClientLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { t } = usePrefs();
  if (!user) return null;

  return (
    <div className="am am-slate am-client">
      <div className="shell">
        <aside className="sidebar">
          <Link to={paths.clientHome} aria-label={t('Borek Flow home')}>
            <img className="logo" src={flowLogo} alt="Borek Flow" />
          </Link>
          <nav className="nav" aria-label={t('Main')}>
            <NavLink to={paths.clientHome} end className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Dashboard')}</NavLink>
            <NavLink to={paths.clientProjects} className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Projects')}</NavLink>
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
              <UserMenu />
            </div>
          </header>
          <main className="content">
            <div className="fit cp">
              <Toast><Outlet /></Toast>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
