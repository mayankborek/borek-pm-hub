import { api } from '@/shared/api/client';
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

const toUser = (u: UserOut): User => ({ id: u.id, name: u.name, email: u.email, role: u.role as Role });

/**
 * Phase 1 (AUTH_MODE=dev): the backend lists seeded users and trusts X-Dev-User-Id.
 * The password is not checked in this mode. Entra ID sign-in plugs in behind the same two functions.
 */
export async function signInWithPassword(email: string, _password: string): Promise<User> {
  const users = await api<UserOut[]>('/auth/dev-users');
  const found = users.find((u) => u.email.toLowerCase() === email.trim().toLowerCase());
  if (!found) throw new NoAccessError();
  return toUser(found);
}

export async function signInWithMicrosoft(): Promise<User> {
  // Needs the Entra tenant/client configuration and a token flow; not available yet.
  throw new ProviderUnavailableError();
}

/** GET /auth/me: the server's view of the signed-in user (role included). Rejects with ApiError(401) if the session is invalid. */
export async function fetchMe(): Promise<User> {
  return toUser(await api<UserOut>('/auth/me'));
}
