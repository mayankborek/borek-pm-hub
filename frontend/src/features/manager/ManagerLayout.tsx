import { Link, NavLink, Outlet } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import logo from '@/assets/borek-flow-portal-logo.svg';
import { initialsOf } from '@/features/client/format';
import { Notifications } from '@/features/client/Notifications';
import { Toast } from '@/features/accountManager/AccountManagerLayout';
import '@/features/accountManager/am.css';
import '@/features/client/clientPortal.css';

/** Manager shell (manager.png): sidebar, "Dashboard" top bar with bell and the signed-in user. */
export function ManagerLayout() {
  const { user } = useAuth();
  const { t } = usePrefs();
  if (!user) return null;

  return (
    <div className="am am-slate">
      <div className="shell">
        <aside className="sidebar">
          <Link to={paths.managerHome} aria-label={t('Borek Flow home')}>
            <img className="logo" src={logo} alt="BOREK Solutions Group" />
          </Link>
          <div className="sub">Borek Flow</div>
          <nav className="nav" aria-label={t('Main')}>
            <NavLink to={paths.managerHome} end className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Dashboard')}</NavLink>
            <NavLink to={paths.projects}>{t('Projects')}</NavLink>
          </nav>
        </aside>
        <div className="main">
          <header className="topbar">
            <h2>{t('Dashboard')}</h2>
            <div className="right">
              <span className="cp cp-tools">
                <Notifications />
              </span>
              <Link to={paths.profile} className="user">
                <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>
                {user.name}
              </Link>
            </div>
          </header>
          <main className="content">
            <div className="fit">
              <Toast><Outlet /></Toast>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
