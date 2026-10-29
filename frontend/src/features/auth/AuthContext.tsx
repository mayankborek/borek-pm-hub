import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ApiError,
  hasApiToken,
  hasStoredCredentials,
  setApiToken,
  setApiUser,
  setUnauthorizedHandler,
} from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { fetchMe, logoutOnServer, NoAccessError } from './authService';
import type { User } from './types';

// Earlier builds kept the whole user (role included) here. It is never read; just clear it.
const LEGACY_USER_KEY = 'borek.user';
try {
  sessionStorage.removeItem(LEGACY_USER_KEY);
} catch {
  /* ignore */
}

/** loading: a stored credential is being checked; unavailable: the check failed for a reason other than 401. */
type Status = 'ready' | 'loading' | 'unavailable';

interface AuthValue {
  /** Only ever set from a server response, never from browser storage. */
  user: User | null;
  signIn: (user: User) => void;
  /** Ends the server sessions first (credentials are still attached), then clears local state. */
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { t } = usePrefs();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status>(() => (hasStoredCredentials() ? 'loading' : 'ready'));
  const [attempt, setAttempt] = useState(0);

  const signIn = useCallback((next: User) => {
    // With a bearer token the dev user id header is ignored, so it is not stored.
    if (!hasApiToken()) setApiUser(next.id);
    setUser(next);
    setStatus('ready');
  }, []);

  const clearSession = useCallback(() => {
    setApiUser(null);
    setApiToken(null);
    setUser(null);
    setStatus('ready');
    qc.clear();
  }, [qc]);

  const signOut = useCallback(async () => {
    await logoutOnServer();
    clearSession();
  }, [clearSession]);

  useEffect(() => {
    setUnauthorizedHandler(clearSession);
    return () => setUnauthorizedHandler(null);
  }, [clearSession]);

  // A stored credential only resumes a session: the server decides who this is and what role they hold.
  useEffect(() => {
    if (status !== 'loading') return;
    let cancelled = false;
    fetchMe()
      .then((fresh) => {
        if (cancelled) return;
        setUser(fresh);
        setStatus('ready');
      })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof NoAccessError || (e instanceof ApiError && e.status >= 400 && e.status < 500)) clearSession();
        else setStatus('unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, [status, attempt, clearSession]);

  const value = useMemo(() => ({ user, signIn, signOut }), [user, signIn, signOut]);

  if (status === 'loading') {
    return (
      <div role="status" aria-live="polite" style={{ padding: 24 }}>
        {t('Loading…')}
      </div>
    );
  }
  if (status === 'unavailable') {
    return (
      <div role="alert" style={{ padding: 24 }}>
        <p>{t('Could not verify your session.')}</p>
        <button
          type="button"
          onClick={() => {
            setStatus('loading');
            setAttempt((n) => n + 1);
          }}
        >
          {t('Retry')}
        </button>{' '}
        <button type="button" onClick={signOut}>
          {t('Sign out')}
        </button>
      </div>
    );
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
