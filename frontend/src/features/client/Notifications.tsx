import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useClientPortal } from './clientPortalApi';

const bell = (
  <svg width="20" height="20" viewBox="1172 105 20 20" fill="none" aria-hidden="true">
    <path
      d="M1180.33 123.5H1183.67M1187 112.667C1187 111.341 1186.47 110.069 1185.54 109.131C1184.6 108.193 1183.33 107.667 1182 107.667C1180.67 107.667 1179.4 108.193 1178.46 109.131C1177.53 110.069 1177 111.341 1177 112.667C1177 118.5 1174.5 118.5 1174.5 120.167H1189.5C1189.5 118.5 1187 118.5 1187 112.667Z"
      stroke="#5C6178"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

/** Bell button with the notifications popover (closes on outside click, Escape or choosing an item). */
export function Notifications() {
  const { t } = usePrefs();
  const { data } = useClientPortal();
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

  const items = data?.notifications ?? [];
  const unread = items.filter((n) => n.unread).length;

  return (
    <span ref={wrap}>
      <button
        ref={button}
        type="button"
        className="cp-bell"
        aria-label={unread ? t('Notifications ({n} unread)', { n: unread }) : t('Notifications')}
        aria-expanded={open}
        aria-controls="cp-notifications"
        onClick={() => setOpen((v) => !v)}
      >
        {bell}
      </button>
      {open && (
        <div className="cp-notif" id="cp-notifications" role="region" aria-label={t('Notifications')}>
          <h2 className="cp-notif-title">{t('Notifications')}</h2>
          <ul className="cp-notif-list">
            {items.map((n) => (
              <li key={n.id}>
                <Link className={n.unread ? 'cp-notif-item cp-unread' : 'cp-notif-item'} to={n.to} onClick={() => setOpen(false)}>
                  <span className="cp-notif-headline">{t(n.headline)}</span>
                  <span className="cp-notif-meta">{n.meta}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </span>
  );
}
