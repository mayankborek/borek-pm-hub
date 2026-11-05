import { useEffect, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { homeFor, paths, withInvitation } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import ms365Logo from '@/assets/ms365-logo.png';
import { useAuth } from '../AuthContext';
import { InvalidCredentialsError, NoAccessError, signInWithMicrosoft, signInWithPassword } from '../authService';
import type { User } from '../types';
import { ClientAuthShell, useClientLang } from './ClientAuthShell';
import { useInvitation } from './useInvitation';

type View = 'default' | 'error' | 'signing-in' | 'no-access';
type FieldErrors = { email?: string; password?: string };

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const eyeProps = { viewBox: '0 0 20 20', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinejoin: 'round', strokeLinecap: 'round', 'aria-hidden': true } as const;

/** Sign-in for invited clients: same credentials flow as staff, with invitation context and a way to create an account. */
export function ClientLoginPage() {
  const { signIn } = useAuth();
  const { setTheme } = usePrefs();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const { lang, changeLang, t, login } = useClientLang();
  const invitation = useInvitation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [view, setView] = useState<View>('default');
  const [errors, setErrors] = useState<FieldErrors>({});

  // Start from the invited address, without overwriting something the person already typed.
  const invitedEmail = invitation.data?.email;
  useEffect(() => {
    if (invitedEmail) setEmail((current) => current || invitedEmail);
  }, [invitedEmail]);

  const busy = view === 'signing-in';

  const finish = (user: User) => {
    setTheme('light'); // every session starts in the default light theme
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
    if (!EMAIL_RE.test(email)) next.email = login.emailInvalid;
    if (!password) next.password = login.passwordRequired;
    setErrors(next);
    if (next.email || next.password) {
      setView('error');
      return;
    }
    void run(() => signInWithPassword(email, password));
  };

  return (
    <ClientAuthShell lang={lang} busy={busy} help={login.help}>
      <h2>{login.welcome}</h2>
      <p className="sub">{login.sub}</p>

      <button type="button" className="btn" disabled={busy} onClick={() => void run(signInWithMicrosoft)}>
        <span className="ms" aria-hidden="true">
          <img src={ms365Logo} alt="" />
        </span>
        {login.microsoft}
      </button>

      <p className="alt">{t.altLabel}</p>

      <form noValidate onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="email">{login.email}</label>
          <input
            id="email"
            type="email"
            placeholder="name@company.com"
            autoComplete="username"
            value={email}
            disabled={busy}
            aria-invalid={errors.email ? true : undefined}
            aria-describedby={errors.email ? 'email-err' : undefined}
            onChange={(e) => setEmail(e.target.value)}
          />
          {errors.email && <p className="field-err" id="email-err">{errors.email}</p>}
        </div>
        <div className="field">
          <label htmlFor="password">{login.password}</label>
          <div className="pw">
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              value={password}
              disabled={busy}
              aria-invalid={errors.password ? true : undefined}
              aria-describedby={errors.password ? 'pw-err' : undefined}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              type="button"
              className="pw-toggle"
              aria-label={showPassword ? t.hidePassword : t.showPassword}
              aria-pressed={showPassword}
              onClick={() => setShowPassword((s) => !s)}
            >
              {showPassword ? (
                <svg {...eyeProps}>
                  <path d="M8.2 4.4A8.6 8.6 0 0 1 10 4.17C15.3 4.17 18.33 10 18.33 10a14.6 14.6 0 0 1-2.6 3.4M5.5 5.9A14.4 14.4 0 0 0 1.67 10S4.7 15.83 10 15.83c1.1 0 2.1-.25 3-.62" />
                  <path d="M8.2 8.2a2.5 2.5 0 0 0 3.6 3.6M2.5 2.5l15 15" />
                </svg>
              ) : (
                <svg {...eyeProps}>
                  <path d="M1.67 10S4.7 4.17 10 4.17 18.33 10 18.33 10 15.3 15.83 10 15.83 1.67 10 1.67 10Z" />
                  <circle cx="10" cy="10" r="2.5" />
                </svg>
              )}
            </button>
          </div>
          {errors.password && <p className="field-err" id="pw-err">{errors.password}</p>}
        </div>
        <button type="submit" className="btn login" disabled={busy}>
          {busy ? login.signingIn : login.login}
        </button>
        <div className="options">
          <label className="check">
            <input type="checkbox" disabled={busy} /> {login.keepSignedIn}
          </label>
          <a href="#forgot-password">{t.forgot}</a>
        </div>
      </form>

      {view === 'error' && (
        <div className="status error" role="alert">
          <strong>{login.errorTitle}</strong>
          <span>{login.errorText}</span>
        </div>
      )}
      {view === 'no-access' && (
        <div className="status" role="alert">
          <strong>{login.noAccessTitle}</strong>
          <span>{login.noAccessText}</span>
        </div>
      )}
      {busy && (
        <div className="progress" role="progressbar" aria-label={login.signingIn}>
          <span />
        </div>
      )}

      <hr />
      <div className="lang">
        <h3>{login.language}</h3>
        <a href="?lang=en" onClick={(e) => { e.preventDefault(); changeLang('en'); }}>English</a>
        <a href="?lang=de" onClick={(e) => { e.preventDefault(); changeLang('de'); }}>Deutsch</a>
      </div>

      <p className="register" style={{ marginTop: 17 }}>
        <span>{t.newToFlow}</span>
        <Link to={withInvitation(paths.clientCreateAccount, invitation.token)}>{t.createAccount}</Link>
      </p>
    </ClientAuthShell>
  );
}
