import { useState, type FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { homeFor } from '@/app/routes';
import { useAuth } from './AuthContext';
import {
  InvalidCredentialsError,
  NoAccessError,
  signInWithMicrosoft,
  signInWithPassword,
} from './authService';
import type { User } from './types';
import './login.css';

type View = 'default' | 'error' | 'signing-in' | 'no-access';
type FieldErrors = { email?: string; password?: string };

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [view, setView] = useState<View>('default');
  const [errors, setErrors] = useState<FieldErrors>({});

  const busy = view === 'signing-in';

  const finish = (user: User) => {
    signIn(user);
    navigate(from ?? homeFor(user.role), { replace: true });
  };

  const run = async (action: () => Promise<User>) => {
    setView('signing-in');
    try {
      finish(await action());
    } catch (e) {
      setView(e instanceof NoAccessError ? 'no-access' : 'error');
      if (e instanceof InvalidCredentialsError) setErrors({});
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const next: FieldErrors = {};
    if (!EMAIL_RE.test(email)) next.email = 'Email format is invalid.';
    if (!password) next.password = 'Password is required.';
    setErrors(next);
    if (next.email || next.password) {
      setView('error');
      return;
    }
    void run(() => signInWithPassword(email, password));
  };

  return (
    <div className="login-page">
      <div className="page">
        <section className="hero">
          <div className="art" aria-hidden="true" />
          <div>
            <div className="logo">
              BOREK<small>SOLUTIONS GROUP</small>
            </div>
            <div className="product">Borek Flow</div>
          </div>
          <div className="copy">
            <h1>Work, Moving Forward.</h1>
            <p>One workspace for project plans, team tasks, and delivery progress.</p>
          </div>
          <footer>Borek Flow · Secure workspace</footer>
        </section>

        <main className="panel">
          <div className="form-wrap" aria-busy={busy}>
            <h2>Welcome back</h2>
            <p className="sub">
              Sign in with your company account. Your access and workspace will load automatically.
            </p>

            <button type="button" className="btn" disabled={busy} onClick={() => void run(signInWithMicrosoft)}>
              <span className="ms" aria-hidden="true">
                <i />
                <i />
                <i />
                <i />
              </span>
              Continue with Microsoft
            </button>

            <form noValidate onSubmit={onSubmit}>
              <div className="field">
                <label htmlFor="email">Email *</label>
                <input
                  id="email"
                  type="email"
                  placeholder="name@borek.com"
                  autoComplete="username"
                  value={email}
                  disabled={busy}
                  aria-invalid={errors.email ? true : undefined}
                  aria-describedby={errors.email ? 'email-err' : undefined}
                  onChange={(e) => setEmail(e.target.value)}
                />
                {errors.email && (
                  <p className="field-err" id="email-err">
                    {errors.email}
                  </p>
                )}
              </div>
              <div className="field">
                <label htmlFor="password">Password *</label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  disabled={busy}
                  aria-invalid={errors.password ? true : undefined}
                  aria-describedby={errors.password ? 'pw-err' : undefined}
                  onChange={(e) => setPassword(e.target.value)}
                />
                {errors.password && (
                  <p className="field-err" id="pw-err">
                    {errors.password}
                  </p>
                )}
              </div>
              <button type="submit" className="btn login" disabled={busy}>
                {busy ? 'Signing in...' : 'Login'}
              </button>
              <label className="check">
                <input type="checkbox" disabled={busy} /> Keep me signed in on this device
              </label>
            </form>

            {view === 'error' && (
              <div className="status error" role="alert">
                <strong>Check your sign-in details</strong>
                <span>Try again or reset your company password.</span>
              </div>
            )}
            {view === 'no-access' && (
              <div className="status" role="alert">
                <strong>No workspace access</strong>
                <span>Contact your workspace administrator to request an account.</span>
              </div>
            )}
            {busy && (
              <div className="progress" role="progressbar" aria-label="Signing in">
                <span />
              </div>
            )}

            <hr />
            <div className="lang">
              <h3>Language</h3>
              <a href="?lang=en">English</a>
              <a href="?lang=de">Deutsch</a>
            </div>
          </div>
          <p className="help">Need access? Contact your workspace administrator.</p>
        </main>
      </div>
    </div>
  );
}
