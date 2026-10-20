import type { User } from './types';

export class NoAccessError extends Error {}
export class InvalidCredentialsError extends Error {}

/**
 * STUB. Replace with the real calls once the backend auth ticket is merged:
 *   GET /auth/dev-users  -> user picker (Phase 1)
 *   GET /auth/me         -> restore the session
 * Later: Microsoft Entra ID via the same interface.
 */
const SEEDED: User[] = [
  { id: '00000000-0000-4000-8000-000000000001', name: 'Test PM', email: 'pm@borek.com', role: 'pm' },
  { id: '00000000-0000-4000-8000-000000000011', name: 'Dev 1', email: 'dev1@borek.com', role: 'developer' },
];

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function signInWithPassword(email: string, _password: string): Promise<User> {
  await delay(600);
  const user = SEEDED.find((u) => u.email === email.trim().toLowerCase());
  if (!user) throw new NoAccessError();
  return user;
}

export async function signInWithMicrosoft(): Promise<User> {
  await delay(600);
  return SEEDED[0];
}
