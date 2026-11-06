import { useEffect, useRef, type FormEvent, type ReactNode } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Present: the dialog is a form and Enter submits. */
  onSubmit?: () => void;
  /** Narrower confirm layout with a darker backdrop. */
  confirm?: boolean;
}

/** Modal used across the admin console. Escape and a click on the backdrop close it; focus starts on the first field. */
export function Dialog({ title, onClose, onSubmit, confirm, children }: Props) {
  const { t } = usePrefs();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>('input, select, button.ad-btn')?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      prev?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit?.();
  };

  const body = (
    <>
      <h2 id="ad-dlg-title">{t(title)}</h2>
      {children}
    </>
  );

  return (
    <div className={confirm ? 'ad-overlay ad-overlay--confirm' : 'ad-overlay'} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className={confirm ? 'ad-dialog ad-dialog--confirm' : 'ad-dialog'} role="dialog" aria-modal="true" aria-labelledby="ad-dlg-title">
        {onSubmit ? (
          <form onSubmit={submit} noValidate>
            {body}
          </form>
        ) : (
          body
        )}
      </div>
    </div>
  );
}

export function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  const { t } = usePrefs();
  return (
    <label className="ad-field">
      <span>{t(label)}</span>
      {children}
      {error && <em role="alert">{t(error)}</em>}
    </label>
  );
}

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface ConfirmProps {
  title: string;
  text: string;
  confirm: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Confirm modal (see modals.html): a title, one sentence, Cancel and a navy primary action. */
export function ConfirmDialog({ title, text, confirm, busy, onConfirm, onCancel }: ConfirmProps) {
  const { t } = usePrefs();
  return (
    <Dialog title={title} onClose={onCancel} confirm>
      <p className="ad-confirm-text">{t(text)}</p>
      <div className="ad-actions">
        <button type="button" className="ad-btn ad-btn--ghost" onClick={onCancel}>{t('Cancel')}</button>
        <button type="button" className="ad-btn" disabled={busy} onClick={onConfirm}>{t(confirm)}</button>
      </div>
    </Dialog>
  );
}
