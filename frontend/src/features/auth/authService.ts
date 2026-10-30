import { api, ApiError, setApiToken } from '@/shared/api/client';
import type { Role, User } from './types';

export class NoAccessError extends Error {}
export class InvalidCredentialsError extends Error {}
export class ProviderUnavailableError extends Error {}

interface UserOut {
  id: string;
  name: string;
  email: string;
  role: string;
}

const ROLES: readonly Role[] = ['pm', 'developer'];

/** Rejects an unknown role instead of casting it, so the UI never runs with a role it does not understand. */
function toUser(u: UserOut): User {
  if (!ROLES.includes(u.role as Role)) throw new NoAccessError();
  return { id: u.id, name: u.name, email: u.email, role: u.role as Role };
}

interface LoginOut {
  access_token: string;
  user: UserOut;
}

/**
 * POST /auth/login (backend AUTH_MODE=local) checks the password and returns a bearer token.
 * There is no fallback: if the backend is not in local mode the sign-in fails instead of skipping the check.
 * Entra ID sign-in plugs in behind the same two functions.
 */
export async function signInWithPassword(email: string, password: string): Promise<User> {
  try {
    const res = await api<LoginOut>('/auth/login', { method: 'POST', body: JSON.stringify({ email: email.trim(), password }) });
    setApiToken(res.access_token);
    return toUser(res.user);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) throw new InvalidCredentialsError();
    throw e;
  }
}

export async function signInWithMicrosoft(): Promise<User> {
  // Needs the Entra tenant/client configuration and a token flow; not available yet.
  throw new ProviderUnavailableError();
}

/** GET /auth/me: the server's view of the signed-in user (role included). Rejects with ApiError(401) if the session is invalid. */
export async function fetchMe(): Promise<User> {
  return toUser(await api<UserOut>('/auth/me'));
}

/**
 * POST /auth/logout ends all of this user's sessions on the server. Best effort: the local session
 * is cleared by the caller whether or not this succeeds (offline, already expired, or an API without the route).
 */
export async function logoutOnServer(): Promise<void> {
  try {
    await api<void>('/auth/logout', { method: 'POST' });
  } catch {
    /* the caller signs out locally regardless */
  }
}
