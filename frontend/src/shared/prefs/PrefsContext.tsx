import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { DE } from './de';
import { readCookie, writeCookie } from './cookies';

export type Lang = 'en' | 'de';
export type Theme = 'light' | 'dark';

interface Prefs {
  lang: Lang;
  theme: Theme;
  setLang: (l: Lang) => void;
  setTheme: (t: Theme) => void;
  /** Translate an English UI string; `{name}` placeholders are filled from `vars`. */
  t: (text: string, vars?: Record<string, string | number>) => string;
}

const initialLang = (): Lang => (readCookie('lang') === 'de' ? 'de' : 'en');
const initialTheme = (): Theme => (readCookie('theme') === 'dark' ? 'dark' : 'light');

const apply = (lang: Lang, theme: Theme) => {
  document.documentElement.lang = lang;
  document.documentElement.dataset.theme = theme;
};

// Apply before first paint so the page never flashes the wrong theme.
apply(initialLang(), initialTheme());

const PrefsContext = createContext<Prefs | null>(null);

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const [theme, setThemeState] = useState<Theme>(initialTheme);

  useEffect(() => apply(lang, theme), [lang, theme]);

  const setLang = useCallback((l: Lang) => {
    writeCookie('lang', l);
    setLangState(l);
  }, []);
  const setTheme = useCallback((t: Theme) => {
    writeCookie('theme', t);
    setThemeState(t);
  }, []);

  const t = useCallback(
    (text: string, vars?: Record<string, string | number>) => {
      const base = lang === 'de' ? DE[text] ?? text : text;
      return vars ? base.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? '')) : base;
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, theme, setLang, setTheme, t }), [lang, theme, setLang, setTheme, t]);
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs() {
  const ctx = useContext(PrefsContext);
  if (!ctx) throw new Error('usePrefs must be used inside <PrefsProvider>');
  return ctx;
}
