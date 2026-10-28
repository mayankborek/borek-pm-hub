import { useLayoutEffect, useState, type FormEvent } from 'react';
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
import borekLogo from '@/assets/borek-logo.png';
import ms365Logo from '@/assets/ms365-logo.png';
import heroArt from '@/assets/login-hero.jpg';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { writeCookie } from '@/shared/prefs/cookies';
import { LOGIN_STRINGS, initialLang, type Lang } from './loginStrings';
import './login.css';

type View = 'default' | 'error' | 'signing-in' | 'no-access';
type FieldErrors = { email?: string; password?: string };

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function LoginPage() {
  const { signIn } = useAuth();
  const { setTheme } = usePrefs();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [view, setView] = useState<View>('default');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [lang, setLang] = useState<Lang>(initialLang);
  const t = LOGIN_STRINGS[lang];

  const changeLang = (l: Lang) => {
    setLang(l);
    writeCookie('lang', l);
    document.documentElement.lang = l;
  };

  // The login screen is always light, whatever theme is selected; restore it on leave.
  useLayoutEffect(() => {
    const root = document.documentElement;
    const previous = root.dataset.theme;
    root.dataset.theme = 'light';
    return () => {
      if (previous) root.dataset.theme = previous;
    };
  }, []);

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
    if (!EMAIL_RE.test(email)) next.email = t.emailInvalid;
    if (!password) next.password = t.passwordRequired;
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
          <div className="art" aria-hidden="true" style={{ backgroundImage: `url(${heroArt})` }} />
          <div>
            <img className="logo" src={borekLogo} alt="Borek Solutions Group" />
            <div className="product">Borek Flow</div>
          </div>
          <div className="copy">
            <h1>{t.heroTitle}</h1>
            <p>{t.heroText}</p>
          </div>
        <footer>{t.footer}</footer>
        </section>

        <main className="panel">
          <div className="form-wrap" aria-busy={busy}>
            <h2>{t.welcome}</h2>
            <p className="sub">
              {t.sub}
            </p>

            <button type="button" className="btn" disabled={busy} onClick={() => void run(signInWithMicrosoft)}>
              <span className="ms" aria-hidden="true">
                <img src={ms365Logo} alt="" />
              </span>
              {t.microsoft}
            </button>

            <form noValidate onSubmit={onSubmit}>
              <div className="field">
                <label htmlFor="email">{t.email}</label>
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
                <label htmlFor="password">{t.password}</label>
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
                {busy ? t.signingIn : t.login}
              </button>
              <label className="check">
                <input type="checkbox" disabled={busy} /> {t.keepSignedIn}
              </label>
            </form>

            {view === 'error' && (
              <div className="status error" role="alert">
                <strong>{t.errorTitle}</strong>
                <span>{t.errorText}</span>
              </div>
            )}
            {view === 'no-access' && (
              <div className="status" role="alert">
                <strong>{t.noAccessTitle}</strong>
                <span>{t.noAccessText}</span>
              </div>
            )}
            {busy && (
              <div className="progress" role="progressbar" aria-label={t.signingIn}>
                <span />
              </div>
            )}

            <hr />
            <div className="lang">
              <h3>{t.language}</h3>
              <a href="?lang=en" onClick={(e) => { e.preventDefault(); changeLang('en'); }}>English</a>
              <a href="?lang=de" onClick={(e) => { e.preventDefault(); changeLang('de'); }}>Deutsch</a>
            </div>
          </div>
          <p className="help">{t.help}</p>
        </main>
      </div>
    </div>
  );
}
