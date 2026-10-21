import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { Avatar, TaskFilters } from '@/features/tasks/TaskParts';
import {
  emptyFilter,
  useProjectStatuses,
  useStatusActions,
  useProjectTasks,
  type StatusCategory,
  type Task,
  type TaskFilter,
  type TaskPriority,
} from '@/features/tasks/tasksApi';
import { useProjectContext } from './ProjectLayout';
import { QuickCreate } from './QuickCreate';
import { errorText, RenameInput, StatusCreator, StatusMenu } from './StatusParts';
import highestIcon from './assets/priority-highest.svg';
import highIcon from './assets/priority-high.svg';
import mediumIcon from './assets/priority-medium.svg';
import lowIcon from './assets/priority-low.svg';
import gripDots from './assets/grip-dots.svg';
import './board.css';

const PRIORITY: Record<TaskPriority, { label: string; icon: string }> = {
  critical: { label: 'Critical', icon: highestIcon },
  high: { label: 'High', icon: highIcon },
  medium: { label: 'Medium', icon: mediumIcon },
  low: { label: 'Low', icon: lowIcon },
};

/** Named workflow states keep the design's heading colours; other statuses use their category colour. */
const NAME_TONE: Record<string, string> = { 'code review': 'review', testing: 'testing' };

const STATUS_GLYPH: Record<StatusCategory, string> = { backlog: '○', todo: '○', in_progress: '◐', blocked: '⊘', done: '●' };
const shortDate = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
};

interface Column {
  id: string;
  name: string;
  category: StatusCategory;
  tasks: Task[];
}

/** Board tab: one column per project status, planned work only (Backlog-category tasks stay in the Backlog tab). */
export function ProjectBoardPage() {
  const project = useProjectContext();
  const [filter, setFilter] = useState<TaskFilter>(emptyFilter);
  const [composing, setComposing] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);
  const { user } = useAuth();
  const isPm = user?.role === 'pm';
  const actions = useStatusActions(project.id);
  const { data, isPending, isError, refetch } = useProjectTasks(project.id, filter);
  const { data: statuses } = useProjectStatuses(project.id);

  const { columns, shown } = useMemo(() => {
    const tasks = (data?.items ?? []).filter((t) => t.status.category !== 'backlog');
    const cols = new Map<string, Column>();
    (statuses ?? [])
      .filter((s) => s.category !== 'backlog')
      .forEach((s) => cols.set(s.id, { id: s.id, name: s.name, category: s.category, tasks: [] }));
    tasks.forEach((t) => {
      const col = cols.get(t.status.id) ?? { id: t.status.id, name: t.status.name, category: t.status.category, tasks: [] };
      col.tasks.push(t);
      cols.set(col.id, col);
    });
    return { columns: [...cols.values()], shown: tasks.length };
  }, [data, statuses]);

  const all = statuses ?? [];
  const taken = (name: string) => all.some((s) => s.name.toLowerCase() === name.toLowerCase());
  const fail = (err: unknown) => setActionError(errorText(err, 'That change could not be saved. Try again.'));

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

  /** Tasks of a deleted status move to the neighbouring column (previous one, or next for the first). */
  const remove = (index: number) => {
    const col = columns[index];
    const target = columns[index - 1] ?? columns[index + 1];
    const count = all.find((s) => s.id === col.id)?.task_count ?? col.tasks.length;
    const msg = count
      ? `Delete “${col.name}”? Its ${count} task${count === 1 ? '' : 's'} will move to “${target?.name}”.`
      : `Delete “${col.name}”?`;
    if (!window.confirm(msg)) return;
    setActionError('');
    actions.remove.mutate({ id: col.id, moveTo: count ? target?.id : undefined }, { onError: fail });
  };

  if (isPending) return <LoadingState title="Loading board" text="Fetching this project’s tasks." />;
  if (isError) return <ErrorState title="We couldn’t load the board" text="Check your connection and try again." onRetry={() => void refetch()} />;

  const filtered = !!(filter.q.trim() || filter.category || filter.priority || filter.assigneeId);

  return (
    <>
      <TaskFilters filter={filter} onChange={setFilter} tasks={data.items} />
      {columns.length === 0 && !isPm ? (
        <EmptyState
          title={filtered ? 'No matching tasks' : 'No tasks on the board'}
          text={filtered ? 'Try changing or clearing the filters.' : 'Tasks that are planned for this project will appear here.'}
        />
      ) : (
        <>
          <div className="kanban" aria-label="Board">
            {columns.map((col, i) => (
              <section
                key={col.id}
                className={`kcol tone-${NAME_TONE[col.name.toLowerCase()] ?? col.category}${dragOver === i && dragFrom !== i ? ' drop' : ''}`}
                aria-label={col.name}
                onDragOver={(e) => {
                  if (dragFrom === null) return;
                  e.preventDefault();
                  setDragOver(i);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  if (dragFrom !== null) reorder(dragFrom, i);
                  setDragFrom(null);
                  setDragOver(null);
                }}
              >
                <div className="kcol-bar">
                  {isPm && (
                    <span
                      className="grip"
                      draggable
                      title="Drag to reorder"
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
                    <h3 className="kcol-head">{col.name}</h3>
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
                      <Link className="kcard" to={paths.task(t.id)} aria-label={`${t.key} · ${t.title}`}>
                        <span className={`kcard-status st-${t.status.category}`} role="img" aria-label={`Status: ${t.status.name}`} title={t.status.name}>
                          {STATUS_GLYPH[t.status.category]}
                        </span>
                        <span className="kcard-title">{t.title}</span>
                        <span className="kcard-key">{t.key}</span>
                        <span className="kcard-meta">
                          {t.assignee ? (
                            <Avatar user={t.assignee} round />
                          ) : (
                            <span className="avatar round unassigned" title="Unassigned" aria-label="Unassigned">
                              ?
                            </span>
                          )}
                          <img
                            src={PRIORITY[t.priority].icon}
                            alt={PRIORITY[t.priority].label}
                            title={PRIORITY[t.priority].label}
                            width={16}
                            height={16}
                          />
                        </span>
                        <span className="kcard-due">{t.due_date ? `Due ${shortDate(t.due_date)}` : 'No due date'}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
                {composing === col.id ? (
                  <QuickCreate projectId={project.id} statusId={col.id} onClose={() => setComposing(null)} />
                ) : (
                  <button type="button" className="kcol-link" onClick={() => setComposing(col.id)}>
                    + Add task
                  </button>
                )}
              </section>
            ))}
            {isPm && <StatusCreator taken={taken} create={actions.create.mutateAsync} />}
          </div>
          {actionError && (
            <p className="qc-error" role="alert">
              {actionError}
            </p>
          )}
          <p className="kanban-count">
            Showing {shown} of {data.total} tasks
          </p>
        </>
      )}
    </>
  );
}
