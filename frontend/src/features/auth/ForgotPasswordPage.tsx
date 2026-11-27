import { useLayoutEffect, useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { paths } from '@/app/routes';
import { api } from '@/shared/api/client';
import borekLogo from '@/assets/borek-logo.png';
import heroArt from '@/assets/login-hero.jpg';
import './login.css';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Password recovery (Figma "Profile and recovery"): ask for the work email, then tell the person to check the inbox. */
export function ForgotPasswordPage() {
  const prefill = (useLocation().state as { email?: string } | null)?.email ?? '';
  const [email, setEmail] = useState(prefill);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  useLayoutEffect(() => {
    const root = document.documentElement;
    const previous = root.dataset.theme;
    root.dataset.theme = 'light';
    return () => {
      if (previous) root.dataset.theme = previous;
    };
  }, []);

  const send = async () => {
    setBusy(true);
    try {
      // The answer is the same whether or not the address has an account.
      await api<void>('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email: email.trim() }) });
      setSent(true);
    } catch {
      setError('We couldn’t send the link. Try again in a moment.');
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!EMAIL_RE.test(email.trim())) return setError('Enter a valid email address.');
    setError('');
    void send();
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
            {sent ? (
              <>
                <h2>Check your email</h2>
                <p className="sub">If an account exists for this email, you’ll receive a password reset link.</p>
                <div className="note">
                  <b>Check your inbox and spam folder.</b>
                  Use the most recent email to reset your password. The link works once and expires after an hour.
                </div>
                <button type="button" className="btn login" disabled={busy} onClick={() => void send()}>
                  {busy ? 'Sending...' : 'Resend reset link'}
                </button>
                {error && <p className="field-err" role="alert">{error}</p>}
              </>
            ) : (
              <>
                <h2>Forgot password?</h2>
                <p className="sub">Enter your work email and we’ll send you a link to reset your password.</p>
                <form noValidate onSubmit={onSubmit}>
                  <div className="field">
                    <label htmlFor="forgot-email">Work email *</label>
                    <input
                      id="forgot-email"
                      type="email"
                      placeholder="name@borek.com"
                      autoComplete="email"
                      value={email}
                      disabled={busy}
                      aria-invalid={error ? true : undefined}
                      aria-describedby={error ? 'forgot-err' : undefined}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        setError('');
                      }}
                    />
                    {error && <p className="field-err" id="forgot-err" role="alert">{error}</p>}
                  </div>
                  <button type="submit" className="btn login" disabled={busy || !!error}>
                    {busy ? 'Sending...' : 'Send reset link'}
                  </button>
                </form>
              </>
            )}
            <Link className="back-link" to={paths.login}>← Back to sign in</Link>
            <p className="help" style={{ marginTop: 32 }}>
              <b style={{ display: 'block', marginBottom: 8 }}>Using a Microsoft company account?</b>
              Manage your password through your organization.
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
