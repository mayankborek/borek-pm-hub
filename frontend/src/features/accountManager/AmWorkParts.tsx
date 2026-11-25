import { usePrefs } from '@/shared/prefs/PrefsContext';
import type { WorkPriority } from '@/features/client/types';
import { PRIORITY_COLOR, PRIORITY_LABEL, avatarColor, initialsOf, priorityPath, statusColor } from './amWork';

export function PriorityMark({ priority, label = true }: { priority: WorkPriority; label?: boolean }) {
  const { t } = usePrefs();
  return (
    <span className="wk-pri" style={{ color: PRIORITY_COLOR[priority] }}>
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={priorityPath(priority)} />
      </svg>
      {label ? t(PRIORITY_LABEL[priority]) : <span className="sr-only">{t(PRIORITY_LABEL[priority])}</span>}
    </span>
  );
}

export function Person({ name, label = true }: { name: string | null; label?: boolean }) {
  const { t } = usePrefs();
  if (!name) return <span className="wk-person muted">{label ? t('Unassigned') : '–'}</span>;
  return (
    <span className="wk-person" title={name}>
      <span className="wk-av" style={{ background: avatarColor(name) }}>{initialsOf(name)}</span>
      {label && name}
    </span>
  );
}

export const StatusText = ({ status }: { status: string }) => {
  const { t } = usePrefs();
  return <span style={{ color: statusColor(status) }}>{t(status)}</span>;
};
