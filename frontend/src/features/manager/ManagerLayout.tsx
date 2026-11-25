import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import flowLogo from '@/assets/borek-flow-nav-white.svg';
import solutionsLogo from '@/assets/borek-solutions-nav-white.svg';
import { initialsOf } from '@/features/client/format';
import { Notifications } from '@/features/client/Notifications';
import { Toast } from '@/features/accountManager/AccountManagerLayout';
import '@/features/accountManager/am.css';
import '@/features/client/clientPortal.css';
import '@/features/client/slateRounded.css';

/** Top bar title per screen (borek_screens.html): the project tabs are titled by their section. */
function titleFor(pathname: string) {
  if (pathname === paths.managerHome) return 'Dashboard';
  if (pathname.startsWith(paths.managerProfile)) return 'Profile';
  if (pathname === paths.managerTeam) return 'Team';
  if (/^\/manager\/projects\/[^/]+\/?$/.test(pathname)) return 'Overview';
  if (/^\/manager\/projects\/[^/]+\/reports\/[^/]+\/?$/.test(pathname)) return 'Report details';
  if (/^\/manager\/projects\/[^/]+\/milestones\/?$/.test(pathname)) return 'Milestones';
  if (/^\/manager\/projects\/[^/]+\/reports\/?$/.test(pathname)) return 'Reports';
  if (/^\/manager\/projects\/[^/]+\/stakeholders\/?$/.test(pathname)) return 'Stakeholders';
  if (/^\/manager\/projects\/[^/]+\/change-requests\/?$/.test(pathname)) return 'Change Requests';
  return 'Projects';
}

/** Manager shell (borek_screens.html): sidebar (Dashboard, Projects, Team), titled top bar with bell and the signed-in user. */
export function ManagerLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { t } = usePrefs();
  if (!user) return null;

  return (
    <div className="am am-slate am-client">
      <div className="shell">
        <aside className="sidebar">
          <Link to={paths.managerHome} aria-label={t('Borek Flow home')}>
            <img className="logo" src={flowLogo} alt="Borek Flow" />
          </Link>
          <nav className="nav" aria-label={t('Main')}>
            <NavLink to={paths.managerHome} end className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Dashboard')}</NavLink>
            <NavLink to={paths.managerProjects} className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Projects')}</NavLink>
            <NavLink to={paths.managerTeam} className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Team')}</NavLink>
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
              <Link to={paths.managerProfile} className="user">
                <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>
                {user.name}
              </Link>
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
