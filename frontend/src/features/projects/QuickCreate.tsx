import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { ApiError } from '@/shared/api/client';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Avatar } from '@/features/tasks/TaskParts';
import { useAssignableUsers, useCreateTask, useProjectMembers, type TaskPriority } from '@/features/tasks/tasksApi';
import highestIcon from './assets/priority-highest.svg';
import highIcon from './assets/priority-high.svg';
import mediumIcon from './assets/priority-medium.svg';
import lowIcon from './assets/priority-low.svg';
import lowestIcon from './assets/priority-lowest.svg';

const PRIORITIES: { key: TaskPriority; label: string; icon: string }[] = [
  { key: 'highest', label: 'Highest', icon: highestIcon },
  { key: 'high', label: 'High', icon: highIcon },
  { key: 'medium', label: 'Medium', icon: mediumIcon },
  { key: 'low', label: 'Low', icon: lowIcon },
  { key: 'lowest', label: 'Lowest', icon: lowestIcon },
];

/** Inline task composer at the foot of a Board column (Figma "Task quick composer · Inline"). */
export function QuickCreate({ projectId, statusId, onClose }: { projectId: string; statusId: string; onClose: () => void }) {
  const { t } = usePrefs();
  const [title, setTitle] = useState('');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [due, setDue] = useState('');
  const [assigneeId, setAssigneeId] = useState('');
  const dueRef = useRef<HTMLInputElement>(null);
  const isPm = useAuth().user?.role === 'pm';
  // A PM can pick any developer (they join the project when assigned); a developer only gets themselves.
  const projectMembers = useProjectMembers(projectId);
  const developers = useAssignableUsers('', isPm);
  const people = isPm
    ? (developers.data?.items ?? []).map((u) => ({ user_id: u.id, name: u.name, email: u.email }))
    : (projectMembers.data ?? []);
  const create = useCreateTask(projectId);

  const assignee = people.find((m) => m.user_id === assigneeId);
  const canCreate = title.trim().length > 0 && !create.isPending;
  const priorityIcon = PRIORITIES.find((p) => p.key === priority)!.icon;

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!canCreate) return;
    create.mutate(
      { title: title.trim(), status_id: statusId, priority, due_date: due || null, assignee_id: assigneeId || null },
      { onSuccess: onClose },
    );
  };
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  };

  return (
    <form className="qc-wrap" onSubmit={submit} onKeyDown={onKeyDown}>
      <div className="qc">
        <input
          className="qc-title"
          autoFocus
          placeholder={t('What needs to be done?')}
          aria-label={t('Task title')}
          maxLength={300}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <div className="qc-fields">
          <label className="qc-priority" title={`${t('Priority')}: ${t(PRIORITIES.find((p) => p.key === priority)!.label)}`}>
            <img src={priorityIcon} alt="" width={16} height={16} />
            <span aria-hidden="true">⌄</span>
            <select aria-label={t('Priority')} value={priority} onChange={(e) => setPriority(e.target.value as TaskPriority)}>
              {PRIORITIES.map((p) => (
                <option key={p.key} value={p.key}>
                  {t(p.label)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="qc-icon"
            aria-label={due ? `${t('Due date')} ${due}` : t('Set due date')}
            title={due || t('Due date')}
            onClick={() => dueRef.current?.showPicker?.()}
          >
            ▦
            <input ref={dueRef} type="date" tabIndex={-1} aria-hidden="true" value={due} onChange={(e) => setDue(e.target.value)} />
          </button>
          <label className="qc-assignee" title={assignee ? assignee.name : t('Unassigned')}>
            {assignee ? (
              <Avatar user={{ id: assignee.user_id, name: assignee.name, email: assignee.email }} round />
            ) : (
              <span className="avatar round unassigned" aria-hidden="true">
                ?
              </span>
            )}
            <select aria-label={t('Assignee')} value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)}>
              <option value="">{t('Unassigned')}</option>
              {people.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="qc-create" disabled={!canCreate} aria-label={t('Create task')} title={t('Create task (Enter)')}>
            ↵
          </button>
        </div>
      </div>
      {create.isError && (
        <p className="qc-error" role="alert">
          {create.error instanceof ApiError ? create.error.message : t('Could not create the task. Try again.')}
        </p>
      )}
      <button type="button" className="kcol-link" onClick={onClose}>
        {t('Cancel')}
      </button>
    </form>
  );
}
