import type { ReactNode } from 'react';
import './ui.css';

export function LoadingState({ title = 'Loading', text }: { title?: string; text?: string }) {
  return (
    <section className="state" aria-busy="true" aria-live="polite">
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      <div className="skel" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
    </section>
  );
}

export function EmptyState({ title, text, action }: { title: string; text?: string; action?: ReactNode }) {
  return (
    <section className="state center">
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action}
    </section>
  );
}

export function ErrorState({ title, text, onRetry }: { title: string; text?: string; onRetry?: () => void }) {
  return (
    <section className="state center" role="alert">
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          Try again
        </button>
      )}
    </section>
  );
}
