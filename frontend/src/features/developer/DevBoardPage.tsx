import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useProjectContext } from '@/features/projects/ProjectLayout';
import { useCreateTask, useMoveTask, useProjectStatuses, useProjectTasks, type StatusCategory, type Task } from '@/features/tasks/tasksApi';
import { Avatar, FilterBar, PriorityMark, fmtDate, statusTone, useDevFilter, useEscape } from './devUi';

interface Column {
  id: string;
  name: string;
  category: StatusCategory;
  tasks: Task[];
}

/** "+ Add task" at the foot of a column: a title-only composer that assigns the new task to the developer. */
function AddTask({ projectId, statusId, onClose }: { projectId: string; statusId: string; onClose: () => void }) {
  const { t } = usePrefs();
  const { user } = useAuth();
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');
  const create = useCreateTask(projectId);
  useEscape(onClose);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    create.mutate(
      { title: title.trim(), status_id: statusId, assignee_id: user?.id ?? null },
      { onSuccess: onClose, onError: (err) => setError(describeApiError(err, t('Could not create the task. Try again.'))) },
    );
  };
  return (
    <form className="dv-compose" onSubmit={submit}>
      <input autoFocus maxLength={300} placeholder={t('What needs to be done?')} aria-label={t('Task title')} value={title} onChange={(e) => setTitle(e.target.value)} />
      {error && <p role="alert">{error}</p>}
      <div>
        <button type="button" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="on" disabled={!title.trim() || create.isPending}>{t('Add task')}</button>
      </div>
    </form>
  );
}

/** Board tab (borek-flow-screens): one grey column per status with white task cards and a dashed "+ Add task". */
export function DevBoardPage() {
  const { t } = usePrefs();
  const { user } = useAuth();
  const project = useProjectContext();
  const f = useDevFilter();
  const [composing, setComposing] = useState<string | null>(null);
  const [dragTask, setDragTask] = useState<Task | null>(null);
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [error, setError] = useState('');
  const { data, isPending, isError, refetch } = useProjectTasks(project.id, f.filter);
  const { data: statuses } = useProjectStatuses(project.id);
  const move = useMoveTask();

  const columns = useMemo(() => {
    const cols = new Map<string, Column>();
    (statuses ?? []).filter((s) => s.category !== 'backlog').forEach((s) => cols.set(s.id, { id: s.id, name: s.name, category: s.category, tasks: [] }));
    (data?.items ?? []).filter((x) => x.status.category !== 'backlog').forEach((x) => {
      const col = cols.get(x.status.id) ?? { id: x.status.id, name: x.status.name, category: x.status.category, tasks: [] };
      col.tasks.push(x);
      cols.set(col.id, col);
    });
    return [...cols.values()];
  }, [data, statuses]);

  // A developer moves only the tasks assigned to them (the backend enforces the same).
  const canMove = (x: Task) => x.assignee?.id === user?.id;
  const drop = (col: Column) => {
    const task = dragTask;
    setDragTask(null);
    setDragOver(null);
    if (!task || task.status.id === col.id || !canMove(task)) return;
    let reason: string | undefined;
    if (col.category === 'blocked') {
      reason = window.prompt(t('Why is {key} blocked?', { key: task.key }))?.trim();
      if (!reason) return;
    }
    setError('');
    move.mutate({ task, statusId: col.id, reason }, { onError: (e) => setError(describeApiError(e, t('That change could not be saved. Try again.'))) });
  };

  if (isPending) return <LoadingState title="Loading board" text="Fetching this project’s tasks." />;
  if (isError) return <ErrorState title="We couldn’t load the board" text="Check your connection and try again." onRetry={() => void refetch()} />;

  return (
    <>
      <FilterBar f={f} statuses={(statuses ?? []).filter((s) => s.category !== 'backlog')} />
      <div className="dv-board" aria-label={t('Board')}>
        {columns.map((col) => (
          <section
            key={col.id}
            className={dragOver === col.id && dragTask && dragTask.status.id !== col.id ? 'dv-col drop' : 'dv-col'}
            aria-label={col.name}
            onDragOver={(e) => {
              if (!dragTask) return;
              e.preventDefault();
              setDragOver(col.id);
            }}
            onDrop={(e) => {
              e.preventDefault();
              drop(col);
            }}
          >
            <h3 style={{ color: statusTone(col.name, col.category) }}>{t(col.name)}</h3>
            <ul>
              {col.tasks.map((x) => (
                <li key={x.id}>
                  <Link
                    className="dv-card"
                    to={paths.task(x.id)}
                    aria-label={`${x.key} · ${x.title}`}
                    draggable={canMove(x)}
                    onDragStart={(e) => {
                      e.dataTransfer.effectAllowed = 'move';
                      e.dataTransfer.setData('text/plain', x.key); // Firefox only starts a drag when data is set
                      setDragTask(x);
                    }}
                    onDragEnd={() => {
                      setDragTask(null);
                      setDragOver(null);
                    }}
                  >
                    <b>{x.title}</b>
                    <span className="dv-card-row">
                      {x.assignee ? <Avatar name={x.assignee.name} /> : <span className="dv-av none" aria-hidden="true">?</span>}
                      <PriorityMark priority={x.priority} label={false} />
                    </span>
                    <small>{x.due_date ? t('Due {date}', { date: fmtDate(x.due_date, false) }) : t('No due date')}</small>
                  </Link>
                </li>
              ))}
            </ul>
            {composing === col.id ? (
              <AddTask projectId={project.id} statusId={col.id} onClose={() => setComposing(null)} />
            ) : (
              <button type="button" className="dv-add" onClick={() => setComposing(col.id)}>+ {t('Add task')}</button>
            )}
          </section>
        ))}
      </div>
      {error && <p className="dv-error" role="alert">{error}</p>}
    </>
  );
}
