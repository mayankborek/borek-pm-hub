import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { TaskFilters } from '@/features/tasks/TaskParts';
import { isFiltered, useUrlFilter } from '@/features/tasks/useUrlFilter';
import {
  useProjectStatuses,
  useStatusActions,
  useMoveTask,
  usePatchTask,
  useActiveSprintId,
  useProjectTasks,
  type StatusCategory,
  type Task,
  type TaskPage,
} from '@/features/tasks/tasksApi';
import { useProjectContext } from './ProjectLayout';
import { CardAssignee, CardPriority } from './CardPickers';
import { QuickCreate } from './QuickCreate';
import { SprintBar } from './SprintBar';
import { errorText, RenameInput, StatusCreator, StatusMenu } from './StatusParts';
import gripDots from './assets/grip-dots.svg';
import './board.css';

/** Named workflow states keep the design's heading colours; other statuses use their category colour. */
const NAME_TONE: Record<string, string> = { 'code review': 'review', testing: 'testing' };

const shortDate = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(document.documentElement.lang === 'de' ? 'de-DE' : 'en-GB', { day: 'numeric', month: 'short' });
};

interface Column {
  id: string;
  name: string;
  category: StatusCategory;
  tasks: Task[];
}

const NO_TASKS: TaskPage = { items: [], total: 0, page: 1, page_size: 0 };

/** Board tab: one column per project status, planned work only (Backlog-category tasks stay in the Backlog tab). */
export function ProjectBoardPage() {
  const { t: tr } = usePrefs();
  const project = useProjectContext();
  const { filter, applied, setFilter, clear } = useUrlFilter();
  const [composing, setComposing] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);
  const [dragTask, setDragTask] = useState<Task | null>(null);
  const { user } = useAuth();
  const isPm = user?.role === 'pm';
  const moveTask = useMoveTask();
  // Mirrors the backend: a PM moves any card, a developer only the tasks assigned to them.
  const canMove = (t: Task) => isPm || t.assignee?.id === user?.id;
  const patchTask = usePatchTask();
  const edit = (task: Task, patch: Parameters<typeof patchTask.mutate>[0]['patch']) =>
    patchTask.mutate({ task, patch }, { onError: (e) => setActionError(errorText(e, tr('Could not update the task. Try again.'))) });
  const actions = useStatusActions(project.id);
  // The board shows only the active sprint's tasks; with no active sprint it is empty.
  const activeSprint = useActiveSprintId(project.id);
  const activeId = activeSprint.data;
  const tasksQuery = useProjectTasks(project.id, applied, { sprintId: activeId ?? undefined, enabled: !!activeId });
  const { data: tasksData, isError: tasksError, refetch: refetchTasks } = tasksQuery;
  const data = (activeId ? tasksData : undefined) ?? NO_TASKS;
  const isPending = activeSprint.isPending || (!!activeId && tasksQuery.isPending);
  const isError = activeSprint.isError || tasksError;
  const refetch = () => {
    void activeSprint.refetch();
    void refetchTasks();
  };
  const { data: statuses } = useProjectStatuses(project.id);

  const { columns } = useMemo(() => {
    const tasks = data.items; // already limited to the active sprint by the server
    const cols = new Map<string, Column>();
    (statuses ?? [])
      .filter((s) => s.category !== 'backlog')
      .forEach((s) => cols.set(s.id, { id: s.id, name: s.name, category: s.category, tasks: [] }));
    tasks.forEach((t) => {
      const col = cols.get(t.status.id) ?? { id: t.status.id, name: t.status.name, category: t.status.category, tasks: [] };
      col.tasks.push(t);
      cols.set(col.id, col);
    });
    return { columns: [...cols.values()] };
  }, [data, statuses]);

  const all = statuses ?? [];
  const taken = (name: string) => all.some((s) => s.name.toLowerCase() === name.toLowerCase());
  const fail = (err: unknown) => setActionError(errorText(err, tr('That change could not be saved. Try again.')));

  /**
   * Moves a column to a new place among the visible ones. The project-wide order also holds Backlog statuses,
   * so the reordered columns are written back into the slots the visible columns already occupy.
   */
  const reorder = (from: number, to: number) => {
    if (from === to) return;
    const visible = columns.map((c) => c.id);
    const [moved] = visible.splice(from, 1);
    visible.splice(to, 0, moved);
    const shownIds = new Set(visible);
    let next = 0;
    const ids = all.map((s) => (shownIds.has(s.id) ? visible[next++] : s.id));
    setActionError('');
    actions.reorder.mutate(ids, { onError: fail });
  };
  const move = (index: number, dir: -1 | 1) => reorder(index, index + dir);

  /** Moves a card into a column; a blocked column asks for the reason the backend requires. */
  const moveCard = (task: Task, col: Column) => {
    if (task.status.id === col.id || !canMove(task)) return;
    let reason: string | undefined;
    if (col.category === 'blocked') {
      reason = window.prompt(tr('Why is {key} blocked?', { key: task.key }))?.trim();
      if (!reason) return;
    }
    setActionError('');
    moveTask.mutate({ task, statusId: col.id, reason }, { onError: fail });
  };

  /** Tasks of a deleted status move to the neighbouring column (previous one, or next for the first). */
  const remove = (index: number) => {
    const col = columns[index];
    const target = columns[index - 1] ?? columns[index + 1];
    const count = all.find((s) => s.id === col.id)?.task_count ?? col.tasks.length;
    const msg = count
      ? tr(count === 1 ? 'Delete “{name}”? Its {n} task will move to “{target}”.' : 'Delete “{name}”? Its {n} tasks will move to “{target}”.', {
          name: col.name,
          n: count,
          target: target?.name ?? '',
        })
      : tr('Delete “{name}”?', { name: col.name });
    if (!window.confirm(msg)) return;
    setActionError('');
    actions.remove.mutate({ id: col.id, moveTo: count ? target?.id : undefined }, { onError: fail });
  };

  if (isPending) return <LoadingState title="Loading board" text="Fetching this project’s tasks." />;
  if (isError) return <ErrorState title="We couldn’t load the board" text="Check your connection and try again." onRetry={() => void refetch()} />;

  const filtered = isFiltered(applied);

  return (
    <>
      <TaskFilters filter={filter} onChange={setFilter} onClear={clear} tasks={data.items} combined statuses={statuses} />
      <SprintBar projectId={project.id} projectName={project.name} />
      {columns.length === 0 && !isPm ? (
        <EmptyState
          title={filtered ? 'No matching tasks' : 'No tasks on the board'}
          text={filtered ? 'Try changing or clearing the filters.' : 'Tasks that are planned for this project will appear here.'}
        />
      ) : (
        <>
          <div className="kanban" aria-label={tr('Board')}>
            {columns.map((col, i) => (
              <section
                key={col.id}
                className={`kcol tone-${NAME_TONE[col.name.toLowerCase()] ?? col.category}${dragOver === i && dragFrom !== i && (dragFrom !== null || dragTask?.status.id !== col.id) ? ' drop' : ''}`}
                aria-label={col.name}
                onDragOver={(e) => {
                  if (dragFrom === null && !dragTask) return;
                  e.preventDefault();
                  setDragOver(i);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  if (dragFrom !== null) reorder(dragFrom, i);
                  else if (dragTask) moveCard(dragTask, col);
                  setDragTask(null);
                  setDragFrom(null);
                  setDragOver(null);
                }}
              >
                <div className="kcol-bar">
                  {isPm && (
                    <span
                      className="grip"
                      draggable
                      title={tr('Drag to reorder')}
                      aria-hidden="true"
                      onDragStart={(e) => {
                        e.dataTransfer.effectAllowed = 'move';
                        const card = (e.currentTarget as HTMLElement).closest('section');
                        if (card) e.dataTransfer.setDragImage(card, 16, 16);
                        setDragFrom(i);
                      }}
                      onDragEnd={() => {
                        setDragFrom(null);
                        setDragOver(null);
                      }}
                    >
                      <img src={gripDots} alt="" width={2} height={10} draggable={false} />
                      <img src={gripDots} alt="" width={2} height={10} draggable={false} />
                    </span>
                  )}
                  {renaming === col.id ? (
                    <RenameInput
                      initial={col.name}
                      taken={taken}
                      onCancel={() => setRenaming(null)}
                      onSave={(name) => {
                        setRenaming(null);
                        setActionError('');
                        actions.rename.mutate({ id: col.id, name }, { onError: fail });
                      }}
                    />
                  ) : (
                    <h3 className="kcol-head">{tr(col.name)}</h3>
                  )}
                  {isPm && renaming !== col.id && (
                    <StatusMenu
                      name={col.name}
                      canMoveLeft={i > 0}
                      canMoveRight={i < columns.length - 1}
                      canDelete={all.length > 1}
                      onRename={() => setRenaming(col.id)}
                      onMove={(dir) => move(i, dir)}
                      onDelete={() => remove(i)}
                    />
                  )}
                </div>
                <ul className="kcol-list">
                  {col.tasks.map((t) => (
                    <li key={t.id}>
                      <Link
                        className="kcard"
                        to={paths.task(t.id)}
                        aria-label={`${t.key} · ${t.title}`}
                        draggable={canMove(t)}
                        onDragStart={(e) => {
                          e.dataTransfer.effectAllowed = 'move';
                          e.dataTransfer.setData('text/plain', t.key); // Firefox only starts a drag when data is set
                          setDragTask(t);
                        }}
                        onDragEnd={() => {
                          setDragTask(null);
                          setDragOver(null);
                        }}
                      >
                        <span className="kcard-top">
                          <span className="kchip"><i />{tr(col.name)}</span>
                          <CardPriority task={t} editable={canMove(t)} onChange={(priority) => edit(t, { priority })} />
                        </span>
                        <span className="kcard-title">{t.title}</span>
                        <span className="kcard-foot">
                          <CardAssignee task={t} editable={isPm} onChange={(assignee_id) => edit(t, { assignee_id })} />
                          <span className="kcard-due">{t.due_date ? tr('Due {date}', { date: shortDate(t.due_date) }) : tr('No due date')}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
                {composing === col.id ? (
                  <QuickCreate projectId={project.id} statusId={col.id} onClose={() => setComposing(null)} />
                ) : (
                  <button type="button" className="kcol-link" onClick={() => setComposing(col.id)}>
                    {tr('+ Add task')}
                  </button>
                )}
              </section>
            ))}
            {isPm && <StatusCreator taken={taken} create={(name) => actions.create.mutateAsync(name)} />}
          </div>
          {actionError && (
            <p className="qc-error" role="alert">
              {actionError}
            </p>
          )}
        </>
      )}
    </>
  );
}
