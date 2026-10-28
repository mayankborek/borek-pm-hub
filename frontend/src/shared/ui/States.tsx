import type { ReactNode } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import './ui.css';

export function LoadingState({ title = 'Loading', text }: { title?: string; text?: string }) {
  const { t } = usePrefs();
  return (
    <section className="state" aria-busy="true" aria-live="polite">
      <h3>{t(title)}</h3>
      {text && <p>{t(text)}</p>}
      <div className="skel" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
    </section>
  );
}

export function EmptyState({ title, text, action }: { title: string; text?: string; action?: ReactNode }) {
  const { t } = usePrefs();
  return (
    <section className="state center">
      <h3>{t(title)}</h3>
      {text && <p>{t(text)}</p>}
      {action}
    </section>
  );
}

export function ErrorState({ title, text, onRetry }: { title: string; text?: string; onRetry?: () => void }) {
  const { t } = usePrefs();
  return (
    <section className="state center" role="alert">
      <h3>{t(title)}</h3>
      {text && <p>{t(text)}</p>}
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          {t('Try again')}
        </button>
      )}
    </section>
  );
}
