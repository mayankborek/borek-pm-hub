import { useEffect, useState, type FormEvent } from 'react';
import { ApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useCreateTask, type TaskStatusOption } from './tasksApi';
import './tasks.css';

/** Backlog quick create (Figma "Backlog quick create · Overlay"): a title-only form that adds the task to the Backlog. */
export function QuickCreateTask({ projectId, statuses, onClose }: { projectId: string; statuses?: TaskStatusOption[]; onClose: () => void }) {
  const { t } = usePrefs();
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');
  const create = useCreateTask(projectId);
  const backlog = statuses?.find((s) => s.category === 'backlog');

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', esc);
    return () => document.removeEventListener('keydown', esc);
  }, [onClose]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return setError(t('Task title is required.'));
    create.mutate({ title: title.trim(), status_id: backlog?.id, assignee_id: null }, { onSuccess: onClose });
  };

  return (
    <div className="qc-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="qc-card" role="dialog" aria-modal="true" aria-label={t('Create backlog task')} onSubmit={onSubmit} noValidate>
        <h2>{t('Create backlog task')}</h2>
        <p>{t('New tasks land in Backlog and stay off the Board until planned.')}</p>
        {create.isError && (
          <div className="form-alert" role="alert">
            {create.error instanceof ApiError ? create.error.message : t('Could not create the task. Try again.')}
          </div>
        )}
        <input
          className="input"
          autoFocus
          maxLength={300}
          placeholder={t('What needs to be done?')}
          aria-label={t('Task title *')}
          aria-invalid={!!error}
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            setError('');
          }}
        />
        {error && <span className="field-error">{error}</span>}
        <div className="qc-actions">
          <button type="button" className="btn secondary" onClick={onClose}>
            {t('Cancel')}
          </button>
          <button type="submit" className="btn" disabled={create.isPending}>
            {t(create.isPending ? 'Adding…' : 'Add to backlog')}
          </button>
        </div>
      </form>
    </div>
  );
}
