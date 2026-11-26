import { createContext, useContext, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { usePrefs } from '@/shared/prefs/PrefsContext';

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** The top bar title of the page being shown; pages with a dynamic title (Edit ABC Company) set it. */
export const TitleContext = createContext<(title: string | null) => void>(() => {});
export function useAdminTitle(title: string | null) {
  const set = useContext(TitleContext);
  useEffect(() => {
    set(title);
    return () => set(null);
  }, [set, title]);
}

/** Open/close state for a popover: closes on Escape and on a click anywhere outside `ref`. */
export function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);
  return { open, setOpen, ref };
}

/** Waits for typing to pause so each keystroke is not a request. */
export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function initials(name: string): string {
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length > 1) return (words[0][0] + words[1][0]).toUpperCase();
  return (words[0] ?? '').slice(0, 2).toUpperCase();
}

/** Modal on the dark scrim (modal-*.html). Escape and a click on the backdrop close it; focus starts on the first field. */
export function Modal({
  title,
  width = 540,
  onClose,
  onSubmit,
  children,
}: {
  title: string;
  width?: number;
  onClose: () => void;
  onSubmit?: () => void;
  children: ReactNode;
}) {
  const { t } = usePrefs();
  const ref = useRef<HTMLDivElement>(null);
  const scrim = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>('input:not([readonly]), select, button')?.focus();
    // Escape closes only the modal on top.
    const onKey = (e: KeyboardEvent) => {
      const open = document.querySelectorAll('.bf-scrim');
      if (e.key === 'Escape' && open[open.length - 1] === scrim.current) close.current();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      prev?.focus?.();
    };
  }, []);

  const body = (
    <>
      <h2 id="bf-modal-title">{t(title)}</h2>
      {children}
    </>
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit?.();
  };

  return (
    <div ref={scrim} className="bf-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className="bf-modal" style={{ width }} role="dialog" aria-modal="true" aria-labelledby="bf-modal-title">
        {onSubmit ? <form onSubmit={submit} noValidate>{body}</form> : body}
      </div>
    </div>
  );
}

export function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  const { t } = usePrefs();
  return (
    <label className="bf-field">
      {t(label)}
      {children}
      {error && <em role="alert">{t(error)}</em>}
    </label>
  );
}

export function Back({ to, label = 'Back' }: { to: string; label?: string }) {
  const { t } = usePrefs();
  return <Link className="bf-back bf-muted" to={to}>← {t(label)}</Link>;
}

export function Tabs({ items }: { items: { to: string; label: string; on: boolean }[] }) {
  const { t } = usePrefs();
  return (
    <div className="bf-tabs">
      {items.map((i) => <Link key={i.to} to={i.to} className={i.on ? 'on' : undefined}>{t(i.label)}</Link>)}
    </div>
  );
}

export function Icon({ children, size = 16 }: { children: ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" strokeWidth="1.7" aria-hidden="true">
      {children}
    </svg>
  );
}

/** An invitation link is shown by the server once, so this is the only chance to copy it. */
export function ShareLinkModal({ name, email, url, expiresAt, onClose }: { name: string; email: string; url: string; expiresAt: string; onClose: () => void }) {
  const { t, lang } = usePrefs();
  const [copied, setCopied] = useState(false);
  const expires = new Date(expiresAt).toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      /* clipboard blocked: the link stays selectable in the field */
    }
  };
  return (
    <Modal title="Share invitation link" width={480} onClose={onClose}>
      <p className="bf-muted" style={{ marginTop: 8 }}>{name} · {email}</p>
      <div className="bf-copy">
        <input readOnly value={url} aria-label={t('Sign-in link')} onFocus={(e) => e.currentTarget.select()} />
        <button type="button" className="bf-btn" onClick={copy}>{t(copied ? 'Copied' : 'Copy')}</button>
      </div>
      <p className="bf-muted" style={{ marginTop: 12, fontSize: 12 }}>{t('Send this to the person yourself: on mail or on Teams.')}</p>
      <p className="bf-muted" style={{ marginTop: 6, fontSize: 12 }}>{t('It works once and expires on {date}. It won’t be shown again.', { date: expires })}</p>
      <div className="foot"><button type="button" className="bf-btn primary" onClick={onClose}>{t('Done')}</button></div>
    </Modal>
  );
}

export function ConfirmModal({ title, text, confirm, busy, onConfirm, onCancel }: { title: string; text: string; confirm: string; busy?: boolean; onConfirm: () => void; onCancel: () => void }) {
  const { t } = usePrefs();
  return (
    <Modal title={title} width={480} onClose={onCancel}>
      <p className="bf-muted" style={{ margin: '10px 0 0' }}>{t(text)}</p>
      <div className="foot">
        <button type="button" className="bf-btn" onClick={onCancel}>{t('Cancel')}</button>
        <button type="button" className="bf-btn primary" disabled={busy} onClick={onConfirm}>{t(confirm)}</button>
      </div>
    </Modal>
  );
}
