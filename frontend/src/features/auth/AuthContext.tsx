import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, setApiToken, setApiUser, setUnauthorizedHandler } from '@/shared/api/client';
import { fetchMe } from './authService';
import type { User } from './types';

const STORAGE_KEY = 'borek.user';

interface AuthValue {
  user: User | null;
  signIn: (user: User) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

let loadedUserId: string | null = null;

function loadUser(): User | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const user = raw ? (JSON.parse(raw) as User) : null;
    setApiUser(user?.id ?? null);
    loadedUserId = user?.id ?? null;
    return user;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null>(loadUser);

  const signIn = useCallback((next: User) => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setApiUser(next.id);
    setUser(next);
  }, []);

  const signOut = useCallback(() => {
    sessionStorage.removeItem(STORAGE_KEY);
    setApiUser(null);
    setApiToken(null);
    setUser(null);
    qc.clear();
  }, [qc]);

  useEffect(() => {
    setUnauthorizedHandler(signOut);
    return () => setUnauthorizedHandler(null);
  }, [signOut]);

  // Re-resolve the stored session with the server on load: picks up role changes, drops expired/inactive users.
  useEffect(() => {
    if (!loadedUserId) return;
    fetchMe()
      .then((fresh) => {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(fresh));
        setUser(fresh);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) signOut();
      });
  }, [signOut]);

  const value = useMemo(() => ({ user, signIn, signOut }), [user, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
