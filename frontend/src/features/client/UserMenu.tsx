import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from './format';

const TABLET = '(min-width:601px) and (max-width:1024px)';

function useTablet() {
  const [match, setMatch] = useState(() => window.matchMedia(TABLET).matches);
  useEffect(() => {
    const mq = window.matchMedia(TABLET);
    const onChange = () => setMatch(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return match;
}

/** Top-bar user. Desktop: link to the profile. Tablet: dropdown with Account settings and Log out. */
export function UserMenu() {
  const { user, signOut } = useAuth();
  const { t } = usePrefs();
  const tablet = useTablet();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!user) return null;
  const avatar = <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>;

  if (!tablet) {
    return (
      <Link to={paths.clientProfile} className="user">
        {avatar}
        {user.name}
      </Link>
    );
  }

  return (
    <span ref={wrap} className="cp cp-usermenu-wrap">
      <button ref={button} type="button" className="user" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {avatar}
        {user.name}
      </button>
      {open && (
        <nav className="cp-menu" aria-label={t('User menu')}>
          <div className="cp-menu-user">
            <span className="cp-menu-avatar" aria-hidden="true">{initialsOf(user.name)}</span>
            <div>
              <div className="cp-menu-name">{user.name}</div>
              <div className="cp-menu-email">{user.email}</div>
            </div>
          </div>
          <Link className="cp-menu-item" to={paths.clientProfile} onClick={() => setOpen(false)}>{t('Account settings')}</Link>
          <button type="button" className="cp-menu-item cp-menu-link" onClick={() => { setOpen(false); void signOut(); }}>{t('Log out')}</button>
        </nav>
      )}
    </span>
  );
}
