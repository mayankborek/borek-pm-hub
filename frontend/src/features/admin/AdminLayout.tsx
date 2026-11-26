import { useCallback, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import flowLogo from '@/assets/bf-flow-logo.svg';
import borekLogo from '@/assets/bf-borek-logo.svg';
import { TitleContext, initials, usePopover } from './AdminUi';
import './admin.css';

const NAV = [
  { to: paths.adminUsers, label: 'Users', match: ['/admin/users', '/admin/organisations'] },
  { to: paths.adminAccess, label: 'Access', match: ['/admin/access'] },
];

const titleFor = (pathname: string): string => {
  if (pathname.startsWith('/admin/organisations/new')) return 'New client organisation';
  if (pathname.startsWith('/admin/organisations/')) return 'Edit organisation';
  if (pathname.startsWith('/admin/organisations')) return 'Client organisations';
  if (pathname.startsWith('/admin/access/people')) return 'Manage access';
  if (pathname.startsWith('/admin/access')) return 'Access';
  if (pathname.startsWith('/admin/profile')) return 'Profile';
  return 'Users';
};

/** Admin console shell (borek-flow-html): navy sidebar, white top bar with notifications and the profile menu. */
export function AdminLayout() {
  const { user, signOut } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { t } = usePrefs();
  const [title, setTitle] = useState<string | null>(null);
  const bell = usePopover();
  const profile = usePopover();
  const setPageTitle = useCallback((next: string | null) => setTitle(next), []);
  if (!user) return null;

  return (
    <TitleContext.Provider value={setPageTitle}>
      <div className="bf-app">
        <aside className="bf-side">
          <Link to={paths.adminUsers} aria-label={t('Borek Flow home')}>
            <img className="bf-brand" src={flowLogo} alt="Borek Flow" />
          </Link>
          <nav aria-label={t('Admin')}>
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} className={n.match.some((m) => pathname.startsWith(m)) ? 'on' : undefined}>
                {t(n.label)}
              </NavLink>
            ))}
          </nav>
          <img className="bf-foot" src={borekLogo} alt="Borek Solutions Group" />
        </aside>

        <div className="bf-main">
          <header className="bf-top">
            <h1 className="bf-title">{t(title ?? titleFor(pathname))}</h1>
            <div className="bf-right">
              <div className="bf-anchor" ref={bell.ref}>
                <button type="button" className="bf-bell" aria-label={t('Notifications')} aria-haspopup="menu" aria-expanded={bell.open} onClick={() => { profile.setOpen(false); bell.setOpen((o) => !o); }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" strokeWidth="1.6"><path d="M6 9a6 6 0 0 1 12 0c0 6 2 7 2 8H4c0-1 2-2 2-8M10 21h4" /></svg>
                </button>
                {bell.open && (
                  <div className="bf-menu" role="menu" style={{ right: -125, top: 38, width: 360, padding: 0 }}>
                    <h3 style={{ padding: '20px 18px', borderBottom: '1px solid var(--bf-line)', fontSize: 14 }}>{t('Notifications')}</h3>
                    <div style={{ padding: '16px 18px' }}>
                      <b>{t('You’re all caught up')}</b>
                      <p className="bf-muted" style={{ marginTop: 8, fontSize: 12 }}>{t('No new notifications right now.')}</p>
                    </div>
                  </div>
                )}
              </div>
              <div className="bf-anchor" ref={profile.ref}>
                <button type="button" className="bf-who" aria-haspopup="menu" aria-expanded={profile.open} onClick={() => { bell.setOpen(false); profile.setOpen((o) => !o); }}>
                  <span className="bf-av" aria-hidden="true">{initials(user.name)}</span>
                  {user.name}
                </button>
                {profile.open && (
                  <div className="bf-menu" role="menu" style={{ right: -25, top: 42, width: 224 }}>
                    <div className="bf-person" style={{ padding: '8px 10px 10px', borderBottom: '1px solid var(--bf-line)', marginBottom: 6 }}>
                      <span className="bf-av">{initials(user.name)}</span>
                      <div><b>{user.name}</b><small>{user.email}</small></div>
                    </div>
                    <Link to={paths.adminProfile} role="menuitem" onClick={() => profile.setOpen(false)}>{t('Account settings')}</Link>
                    <button
                      type="button"
                      className="item"
                      role="menuitem"
                      style={{ color: 'var(--bf-blue)' }}
                      onClick={() => void signOut().then(() => navigate(paths.login, { replace: true }))}
                    >
                      {t('Log out')}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </header>
          <Outlet />
        </div>
      </div>
    </TitleContext.Provider>
  );
}
