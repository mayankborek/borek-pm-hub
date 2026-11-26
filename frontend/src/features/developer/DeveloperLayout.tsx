import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initials, usePopover } from '@/features/admin/AdminUi';
import flowLogo from '@/assets/bf-flow-logo.svg';
import borekLogo from '@/assets/bf-borek-logo.svg';
import { useDevNotifications } from './devNotifications';
import '@/features/admin/admin.css';
import './developer.css';

/** Top bar title per screen (borek-flow-screens): Board, Backlog, Overview, Task Details. */
function titleFor(pathname: string) {
  if (pathname === paths.profile) return 'Profile';
  if (pathname === paths.myWork) return 'My Work';
  if (pathname.startsWith(`${paths.tasks}/`)) return 'Task Details';
  if (/^\/projects\/[^/]+\/board\/?$/.test(pathname)) return 'Board';
  if (/^\/projects\/[^/]+\/list\/?$/.test(pathname)) return 'Backlog';
  if (/^\/projects\/[^/]+\/?$/.test(pathname)) return 'Overview';
  return 'Projects';
}

const Bell = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" strokeWidth="1.6"><path d="M6 9a6 6 0 0 1 12 0c0 6 2 7 2 8H4c0-1 2-2 2-8M10 21h4" /></svg>
);

/** Notifications popover (borek-flow-screens "Overlays"): unread count, Mark all as read, one row per event. */
function NotificationsMenu() {
  const { t } = usePrefs();
  const bell = usePopover();
  const feed = useDevNotifications();
  return (
    <div className="bf-anchor" ref={bell.ref}>
      <button
        type="button"
        className="bf-bell"
        aria-label={feed.unread ? t('Notifications ({n} unread)', { n: feed.unread }) : t('Notifications')}
        aria-haspopup="true"
        aria-expanded={bell.open}
        onClick={() => bell.setOpen((o) => !o)}
      >
        <Bell />
      </button>
      {bell.open && (
        <div className="dv-notif" role="region" aria-label={t('Notifications')}>
          <h2>{t('Notifications')}</h2>
          <div className="dv-notif-sub">
            <span>{t('{n} unread', { n: feed.unread })}</span>
            <button type="button" disabled={!feed.unread} onClick={feed.markAllRead}>{t('Mark all as read')}</button>
          </div>
          {feed.items.length === 0 ? (
            <p className="dv-notif-empty">{t('You’re all caught up')}</p>
          ) : (
            <ul>
              {feed.items.map((n) => (
                <li key={n.id}>
                  <Link
                    to={n.to}
                    onClick={() => {
                      if (n.unread) feed.markRead(n.id);
                      bell.setOpen(false);
                    }}
                  >
                    <span className="dv-notif-av" aria-hidden="true">{initials(n.actor || 'BF')}</span>
                    <span className="dv-notif-body">
                      <span>{n.headline}</span>
                      <small>{n.meta}</small>
                    </span>
                    {n.unread && <i className="dv-notif-dot" aria-label={t('Unread')} />}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** Developer shell (borek-flow-screens): navy sidebar with My Work and Projects, white top bar with title, bell and profile. */
export function DeveloperLayout() {
  const { user, signOut } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { t } = usePrefs();
  const profile = usePopover();
  if (!user) return null;

  const onProjects = pathname.startsWith('/projects') || pathname.startsWith(`${paths.tasks}/`);
  const board = /^\/projects\/[^/]+\/board\/?$/.test(pathname);

  return (
    <div className="bf-app dv-app">
      <aside className="bf-side">
        <Link to={paths.myWork} aria-label={t('Borek Flow home')}>
          <img className="bf-brand" src={flowLogo} alt="Borek Flow" />
        </Link>
        <nav aria-label={t('Main')}>
          <NavLink to={paths.myWork} className={pathname === paths.myWork ? 'on' : 'dim'}>{t('My Work')}</NavLink>
          <NavLink to={paths.projects} className={onProjects ? 'on' : 'dim'}>{t('Projects')}</NavLink>
        </nav>
        <img className="bf-foot" src={borekLogo} alt="Borek Solutions Group" />
      </aside>

      <div className={board ? 'bf-main dv-main white' : 'bf-main dv-main'}>
        <header className="bf-top">
          <h1 className="bf-title">{t(titleFor(pathname))}</h1>
          <div className="bf-right">
            <NotificationsMenu />
            <div className="bf-anchor" ref={profile.ref}>
              <button type="button" className="bf-who" aria-haspopup="menu" aria-expanded={profile.open} onClick={() => profile.setOpen((o) => !o)}>
                <span className="bf-av" aria-hidden="true">{initials(user.name)}</span>
                {user.name}
              </button>
              {profile.open && (
                <div className="bf-menu" role="menu" style={{ right: -25, top: 42, width: 224 }}>
                  <Link to={paths.profile} role="menuitem" onClick={() => profile.setOpen(false)}>{t('Profile')}</Link>
                  <button type="button" className="item" role="menuitem" style={{ color: 'var(--bf-blue)' }} onClick={() => void signOut().then(() => navigate(paths.login, { replace: true }))}>
                    {t('Log out')}
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="dv-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
