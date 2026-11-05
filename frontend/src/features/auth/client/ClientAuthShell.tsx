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
  children: ReactNode;
}

/** Brand panel plus content panel shared by every screen of the invite-based client flow. */
export function ClientAuthShell({ lang, busy, help, children }: ShellProps) {
  const t = LOGIN_STRINGS[lang];

  // Like the staff login, these screens are always light; restore the selected theme on leave.
  useLayoutEffect(() => {
    const root = document.documentElement;
    const previous = root.dataset.theme;
    root.dataset.theme = 'light';
    return () => {
      if (previous) root.dataset.theme = previous;
    };
  }, []);

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
            {children}
          </div>
          {help && <p className="help">{help}</p>}
        </main>
      </div>
    </div>
  );
}
