import { useLayoutEffect, useState, type ReactNode } from 'react';
import borekLogo from '@/assets/borek-logo.png';
import heroArt from '@/assets/login-hero.jpg';
import { writeCookie } from '@/shared/prefs/cookies';
import { LOGIN_STRINGS } from '../loginStrings';
import { CLIENT_STRINGS, initialLang, type Lang } from './clientStrings';
import '../login.css';
import './clientAuth.css';

export function useClientLang() {
  const [lang, setLang] = useState<Lang>(initialLang);
  const changeLang = (l: Lang) => {
    setLang(l);
    writeCookie('lang', l);
    document.documentElement.lang = l;
  };
  return { lang, changeLang, t: CLIENT_STRINGS[lang], login: LOGIN_STRINGS[lang] };
}

interface ShellProps {
  lang: Lang;
  busy?: boolean;
  help?: string;
  /** The dark invitation layout (01-invitation.html). */
  invite?: boolean;
  /** Replaces the sentence under the hero title. */
  heroText?: string;
  children: ReactNode;
}

/** Brand panel plus content panel shared by every screen of the invite-based client flow. */
export function ClientAuthShell({ lang, busy, help, invite, heroText, children }: ShellProps) {
  const t = LOGIN_STRINGS[lang];

  // Like the staff login, these screens ignore the selected theme (the invitation is dark, the rest light); restore it on leave.
  useLayoutEffect(() => {
    const root = document.documentElement;
    const previous = root.dataset.theme;
    root.dataset.theme = invite ? 'dark' : 'light';
    return () => {
      if (previous) root.dataset.theme = previous;
    };
  }, [invite]);

  return (
    <div className={invite ? 'login-page invite' : 'login-page'}>
      <div className="page">
        <section className="hero">
          <div className="art" aria-hidden="true" style={{ backgroundImage: `url(${heroArt})` }} />
          <div>
            <img className="logo" src={borekLogo} alt="Borek Solutions Group" />
            <div className="product">Borek Flow</div>
          </div>
          <div className="copy">
            <h1>{t.heroTitle}</h1>
            <p>{heroText ?? t.heroText}</p>
          </div>
          <footer>{t.footer}</footer>
        </section>

        <main className="panel">
          <div className="form-wrap" aria-busy={busy}>
            {children}
          </div>
          {help && <p className="help">{help}</p>}
        </main>
      </div>
    </div>
  );
}
