import { useEffect, useRef, type FormEvent, type ReactNode } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Present: the dialog is a form and Enter submits. */
  onSubmit?: () => void;
}

/** Modal used across the admin console. Escape and a click on the backdrop close it; focus starts on the first field. */
export function Dialog({ title, onClose, onSubmit, children }: Props) {
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
    <div className="ad-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className="ad-dialog" role="dialog" aria-modal="true" aria-labelledby="ad-dlg-title">
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
