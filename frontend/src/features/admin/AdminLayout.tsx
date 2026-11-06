import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import logo from '@/assets/borek-flow-logo.svg';
import { initialsOf } from '@/features/client/format';
import '@/features/client/clientPortal.css';
import './admin.css';

const TITLES: Record<string, string> = {
  [paths.adminUsers]: 'Users',
  [paths.adminOrganisations]: 'Client organisations',
  [paths.adminRoles]: 'Role access',
};

const NAV = [
  { to: paths.adminUsers, label: 'Users' },
  { to: paths.adminOrganisations, label: 'Client organisations' },
  { to: paths.adminRoles, label: 'Role access' },
];

export function AdminLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { lang, setLang, t } = usePrefs();
  const section = `/${pathname.split('/').slice(1, 3).join('/')}`;
  if (!user) return null;

  return (
    <div className="cp ad">
      <aside className="cp-side">
        <Link to={paths.adminUsers} aria-label={t('Borek Flow home')}>
          <img className="cp-logo" src={logo} alt="Borek Solutions Group – Borek Flow" />
        </Link>
        <nav className="cp-nav" aria-label={t('Admin')}>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? 'cp-active' : undefined)}>
              {t(n.label)}
            </NavLink>
          ))}
        </nav>
      </aside>
      <section className="cp-main">
        <header className="cp-top">
          <h1>{t(TITLES[section] ?? 'Users')}</h1>
          <div className="cp-tools">
            <div className="cp-lang" role="group" aria-label={t('Language')}>
              <button type="button" className={lang === 'de' ? 'cp-on' : undefined} aria-pressed={lang === 'de'} onClick={() => setLang('de')}>
                DE
              </button>
              <button type="button" className={lang === 'en' ? 'cp-on' : undefined} aria-pressed={lang === 'en'} onClick={() => setLang('en')}>
                EN
              </button>
            </div>
            <Link className="cp-user" to={paths.profile}>
              <div className="cp-avatar" aria-hidden="true">
                {initialsOf(user.name)}
              </div>
              <span>{user.name}</span>
            </Link>
          </div>
        </header>
        <div className="ad-content">
          <Outlet />
        </div>
      </section>
    </div>
  );
}
