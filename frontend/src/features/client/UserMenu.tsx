import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from './format';

/** Top-bar user dropdown (as on the admin screens): name and email, Account settings, Log out. Shared by every role's shell. */
export function UserMenu({ profilePath = paths.clientProfile }: { profilePath?: string }) {
  const { user, signOut } = useAuth();
  const { t } = usePrefs();
  const navigate = useNavigate();
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

  return (
    <span ref={wrap} className="cp cp-usermenu-wrap">
      <button ref={button} type="button" className="user" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>
        <span className="user-name">{user.name}</span>
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
          <Link className="cp-menu-item" to={profilePath} onClick={() => setOpen(false)}>{t('Account settings')}</Link>
          <button
            type="button"
            className="cp-menu-item cp-menu-link"
            onClick={() => { setOpen(false); void signOut().then(() => navigate(paths.login, { replace: true })); }}
          >
            {t('Log out')}
          </button>
        </nav>
      )}
    </span>
  );
}
