import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useAuth } from '@/features/auth/AuthContext';
import { useNotificationFeed } from './notificationsApi';

const bell = (
  <svg width="20" height="20" viewBox="1172 105 20 20" fill="none" aria-hidden="true">
    <path
      d="M1180.33 123.5H1183.67M1187 112.667C1187 111.341 1186.47 110.069 1185.54 109.131C1184.6 108.193 1183.33 107.667 1182 107.667C1180.67 107.667 1179.4 108.193 1178.46 109.131C1177.53 110.069 1177 111.341 1177 112.667C1177 118.5 1174.5 118.5 1174.5 120.167H1189.5C1189.5 118.5 1187 118.5 1187 112.667Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

/** Bell button with the notifications popover (closes on outside click, Escape or choosing an item). */
export function Notifications() {
  const { t } = usePrefs();
  const role = useAuth().user?.role;
  const feed = useNotificationFeed(role === 'client' || role === 'account_manager' || role === 'manager' || role === 'pm' ? role : undefined);
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

  const { items, unread } = feed;

  return (
    <span ref={wrap} className="cp-tools">
      <button
        ref={button}
        type="button"
        className={unread ? 'cp-bell has-unread' : 'cp-bell'}
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
          <div className="cp-notif-sub">
            <span>{t('{n} unread', { n: unread })}</span>
            <button type="button" onClick={() => feed.markAllRead()}>{t('Mark all as read')}</button>
          </div>
          <ul className="cp-notif-list">
            {items.map((n) => (
              <li key={n.id}>
                <Link className={n.unread ? 'cp-notif-item cp-unread' : 'cp-notif-item'} to={n.to} onClick={() => {
                  if (n.unread) feed.markRead(n.id);
                  setOpen(false);
                }}>
                  <span className="cp-notif-avatar" aria-hidden="true">BF</span>
                  <span className="cp-notif-headline">{t(n.headline)}</span>
                  <span className="cp-notif-meta">{n.meta}</span>
                  <span className="cp-notif-dot" aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </span>
  );
}
