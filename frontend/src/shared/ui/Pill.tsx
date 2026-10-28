import { usePrefs } from '@/shared/prefs/PrefsContext';
import './ui.css';

export type Tone = 'neutral' | 'progress' | 'track' | 'risk' | 'blocked' | 'overdue';

export function Pill({ tone, children }: { tone: Tone; children: string }) {
  const { t } = usePrefs();
  return (
    <span className={`pill ${tone}`}>
      <span className="dot" aria-hidden="true" />
      {t(children)}
    </span>
  );
}

/** Completion bar with a text equivalent for screen readers. */
export function ProgressBar({ percent, label }: { percent: number; label: string }) {
  const value = Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value} aria-label={label}>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${value}%` }} />
      </div>
      <span className="progress-value">{value}%</span>
    </div>
  );
}
