import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import logo from '@/assets/borek-flow-portal-logo.svg';
import { initialsOf } from '@/features/client/format';
import '@/features/accountManager/am.css';
import './admin.css';

const TITLES: Record<string, string> = {
  [paths.adminUsers]: 'Users',
  [paths.adminOrganisations]: 'Client organisations',
  [paths.adminRoles]: 'Role access',
  [paths.adminProfile]: 'Profile',
};

const NAV = [
  { to: paths.adminUsers, label: 'Users' },
  { to: paths.adminOrganisations, label: 'Client organisations' },
  { to: paths.adminRoles, label: 'Role access' },
];

/** Admin console. Same shell as the Account Manager portal: dark sidebar, white top bar with the underlined title, bell and profile. */
export function AdminLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { t } = usePrefs();
  const section = `/${pathname.split('/').slice(1, 3).join('/')}`;
  if (!user) return null;

  return (
    <div className="am">
      <div className="shell">
        <aside className="sidebar">
          <Link to={paths.adminUsers} aria-label={t('Borek Flow home')}>
            <img className="logo" src={logo} alt="BOREK Solutions Group" />
          </Link>
          <div className="sub">Borek Flow</div>
          <nav className="nav" aria-label={t('Admin')}>
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? 'active' : undefined)}>
                {t(n.label)}
              </NavLink>
            ))}
          </nav>
        </aside>

        <div className="main">
          <header className="topbar">
            <h2>{t(TITLES[section] ?? 'Users')}</h2>
            <div className="right">
              <button type="button" className="bell" aria-label={t('Notifications')}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
                  <path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" />
                </svg>
              </button>
              <Link to={paths.adminProfile} className="user">
                <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>
                {user.name}
              </Link>
            </div>
          </header>
          <main className="content">
            <div className="ad">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
