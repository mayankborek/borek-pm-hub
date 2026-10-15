import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { navItems, paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';

export function AppLayout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const items = navItems.filter((i) => i.roles.includes(user.role));

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <strong>BOREK</strong>
          <span>Flow</span>
        </div>
        <nav aria-label="Main">
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
              <span aria-hidden="true" className="nav-icon">
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="user">
            <span className="avatar" aria-hidden="true">
              {user.name.charAt(0)}
            </span>
            <div>
              <div className="user-name">{user.name}</div>
              <div className="user-role">{user.role === 'pm' ? 'Project Manager' : 'Developer'}</div>
            </div>
          </div>
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              signOut();
              navigate(paths.login, { replace: true });
            }}
          >
            Sign out
          </button>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
