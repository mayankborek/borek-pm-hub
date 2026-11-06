import { useLayoutEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { api, ApiError } from '@/shared/api/client';
import borekLogo from '@/assets/borek-logo.png';
import heroArt from '@/assets/login-hero.jpg';
import './login.css';

const MIN_LENGTH = 12; // mirrors the backend's MIN_PASSWORD_LENGTH

/** The invite token travels in the URL fragment so it never reaches a server log; read it once. */
const readToken = () => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '';

/** Landing page of the link an administrator hands over: choose a password, then sign in. */
export function SetPasswordPage() {
  const navigate = useNavigate();
  const [token] = useState(readToken);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(token ? null : 'This link is invalid. Ask your administrator for a new one.');
  const [busy, setBusy] = useState(false);

  useLayoutEffect(() => {
    const root = document.documentElement;
    const previous = root.dataset.theme;
    root.dataset.theme = 'light';
    return () => {
      if (previous) root.dataset.theme = previous;
    };
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (password.length < MIN_LENGTH) return setError(`Use at least ${MIN_LENGTH} characters.`);
    if (password !== confirm) return setError('The passwords do not match.');
    setError(null);
    setBusy(true);
    try {
      const { email } = await api<{ email: string }>('/auth/accept-invite', {
        method: 'POST',
        body: JSON.stringify({ token, password }),
      });
      navigate(paths.login, { replace: true, state: { email } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <div className="page">
        <section className="hero">
          <div className="art" aria-hidden="true" style={{ backgroundImage: `url(${heroArt})` }} />
          <div>
            <img className="logo" src={borekLogo} alt="Borek Solutions Group" />
            <div className="product">Borek Flow</div>
          </div>
        </section>

        <main className="panel">
          <div className="form-wrap" aria-busy={busy}>
            <h2>Set your password</h2>
            <p className="sub">Choose a password to finish setting up your account.</p>

            <form noValidate onSubmit={(e) => void onSubmit(e)}>
              <div className="field">
                <label htmlFor="new-password">New password</label>
                <input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  disabled={busy || !token}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="confirm-password">Confirm password</label>
                <input
                  id="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  disabled={busy || !token}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </div>
              <button type="submit" className="btn login" disabled={busy || !token}>
                {busy ? 'Saving…' : 'Set password'}
              </button>
            </form>

            {error && (
              <div className="status error" role="alert">
                <span>{error}</span>
              </div>
            )}
            <p className="help">
              <Link to={paths.login}>Back to sign in</Link>
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
