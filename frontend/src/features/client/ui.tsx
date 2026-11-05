import type { CSSProperties, ReactNode } from 'react';
import type { UseQueryResult } from '@tanstack/react-query';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import type { Tone } from './labels';

export function Bar({ value, style }: { value: number; style?: CSSProperties }) {
  return (
    <div className="cp-bar" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} style={style}>
      <i style={{ width: `${value}%` }} />
    </div>
  );
}

export function Badge({ tone = 'success', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`cp-badge cp-${tone}`}>{children}</span>;
}

export function Kpi({ label, value, hint, overview }: { label: string; value: ReactNode; hint: string; overview?: boolean }) {
  return (
    <div className={overview ? 'cp-card cp-kpi cp-o' : 'cp-card cp-kpi'}>
      <div className="cp-l">{label}</div>
      <div className="cp-v">{value}</div>
      <div className="cp-d">{hint}</div>
    </div>
  );
}

/** Milestone summary card: reference and name, status badge, dates and progress. */
export function MilestoneCard({
  code,
  name,
  tone,
  badge,
  meta,
  progress,
}: {
  code: string;
  name: string;
  tone: Tone;
  badge: string;
  meta: string;
  progress: number;
}) {
  return (
    <article className="cp-mcard">
      <h4>{code} · {name}</h4>
      <Badge tone={tone}>{badge}</Badge>
      <p>{meta}</p>
      <Bar value={progress} />
    </article>
  );
}

/** Loading, empty and error states for shared information. */
export function LoadingCard() {
  const { t } = usePrefs();
  return (
    <section className="cp-state" aria-busy="true" aria-live="polite">
      <h4>{t('Loading shared information…')}</h4>
      <div className="cp-skel" aria-hidden="true"><i /><i /><i /></div>
    </section>
  );
}

export function EmptyCard({ title = 'No shared items yet', text = 'Published information will appear here when your Project Manager shares it.', action }: { title?: string; text?: string; action?: ReactNode }) {
  const { t } = usePrefs();
  return (
    <section className="cp-state">
      <h4>{t(title)}</h4>
      <p>{t(text)}</p>
      {action}
    </section>
  );
}

export function ErrorCard({ onRetry }: { onRetry: () => void }) {
  const { t } = usePrefs();
  return (
    <section className="cp-state" role="alert">
      <h4>{t('Could not load shared information')}</h4>
      <p>{t('Your information could not be loaded. Please try again.')}</p>
      <button type="button" className="cp-retry" onClick={onRetry}>{t('Try again')}</button>
    </section>
  );
}

/** What a page shows until its query has data: the loading state, or the error state with Try again. */
export function PortalPending({ query }: { query: UseQueryResult<unknown> }) {
  if (query.isError) return <ErrorCard onRetry={() => void query.refetch()} />;
  return <LoadingCard />;
}
