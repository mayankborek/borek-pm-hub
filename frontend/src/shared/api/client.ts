import { env } from '@/shared/config/env';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
  }
}

/** The API's message plus its request_id ({ error: { message }, request_id }), so a failure can be traced in the backend logs. */
export function describeApiError(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  const body = err.body as { error?: { message?: string }; request_id?: string } | undefined;
  const message = body?.error?.message ?? `${fallback} (${err.status})`;
  return body?.request_id ? `${message} (request ${body.request_id})` : message;
}

// Phase 1 auth: the selected seeded user id is sent on every request
// (X-Dev-User-Id). Replaced by a bearer token when Entra ID is added.
// Browser storage holds only these credentials, never profile data or the role: both are editable
// by the user, so they are a way to resume a session, not proof of who someone is or what they may do.
// The server's answer (GET /auth/me) is the only source of identity in the UI.
const DEV_USER_KEY = 'borek.dev-user';
let devUserId: string | null = null;
try {
  devUserId = sessionStorage.getItem(DEV_USER_KEY);
} catch {
  /* storage unavailable: the session just won't survive a reload */
}
export const getApiUser = () => devUserId;
export const setApiUser = (id: string | null) => {
  devUserId = id;
  try {
    if (id) sessionStorage.setItem(DEV_USER_KEY, id);
    else sessionStorage.removeItem(DEV_USER_KEY);
  } catch {
    /* ignore */
  }
};

// AUTH_MODE=local: the bearer token from POST /auth/login, kept for the browser session.
const TOKEN_KEY = 'borek.token';
let apiToken: string | null = null;
try {
  apiToken = sessionStorage.getItem(TOKEN_KEY);
} catch {
  /* storage unavailable: the session just won't survive a reload */
}
export const hasApiToken = () => apiToken !== null;
/** True when a stored credential exists that still has to be checked with the server. */
export const hasStoredCredentials = () => apiToken !== null || devUserId !== null;
export const setApiToken = (token: string | null) => {
  apiToken = token;
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
};

/** Auth headers for the current session: bearer token when signed in with a password, else the dev user id. */
export function applyAuth(headers: Headers) {
  if (apiToken) headers.set('Authorization', `Bearer ${apiToken}`);
  else if (devUserId) headers.set('X-Dev-User-Id', devUserId);
}

let onUnauthorized: (() => void) | null = null;
/** AuthProvider registers this so any 401 ends the session in one place. */
export const setUnauthorizedHandler = (fn: (() => void) | null) => {
  onUnauthorized = fn;
};

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  applyAuth(headers);

  const res = await fetch(`${env.apiBaseUrl}${path}`, { ...init, headers });
  if (!res.ok) {
    if (res.status === 401 && (apiToken || devUserId)) onUnauthorized?.();
    const body = await res.json().catch(() => undefined);
    throw new ApiError(res.status, res.statusText, body);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}
