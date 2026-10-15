import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthContext';
import type { Role } from '@/features/auth/types';
import { homeFor, paths } from './routes';

/** Anonymous users go to /login and come back to where they were headed. */
export function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to={paths.login} replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

/** Signed-in users should not see the login page. */
export function RedirectIfAuthed() {
  const { user } = useAuth();
  if (user) return <Navigate to={homeFor(user.role)} replace />;
  return <Outlet />;
}

/** UX gate only. The backend is the real enforcement of permissions. */
export function RequireRole({ roles }: { roles: Role[] }) {
  const { user } = useAuth();
  if (!user) return null;
  if (!roles.includes(user.role)) return <Navigate to={paths.forbidden} replace />;
  return <Outlet />;
}

/** "/" sends each role to its landing page. */
export function RoleHome() {
  const { user } = useAuth();
  return <Navigate to={user ? homeFor(user.role) : paths.login} replace />;
}
