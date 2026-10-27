import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { formatDate } from '@/features/projects/projectUi';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import type { StatusCategory, Task, TaskFilter, TaskPriority, UserBrief } from './tasksApi';
import './tasks.css';

const AVATAR_COLORS = ['#0d1240', '#124f94', '#5c6178'];
const PRIORITY_LABEL: Record<TaskPriority, string> = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' };
const CATEGORY_LABEL: Record<StatusCategory, string> = {
  backlog: 'Backlog',
  todo: 'To do',
  in_progress: 'In progress',
  blocked: 'Blocked',
  done: 'Done',
};

const colorFor = (id: string) => AVATAR_COLORS[[...id].reduce((n, c) => n + c.charCodeAt(0), 0) % AVATAR_COLORS.length];
const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('');

export function Avatar({ user, round }: { user: UserBrief; round?: boolean }) {
  return (
    <span className={round ? 'avatar round' : 'avatar'} style={{ background: colorFor(user.id) }} aria-hidden="true">
      {initials(user.name)}
    </span>
  );
}

export function TaskRow({
  task,
  showProject,
  selected,
  onSelect,
  onDelete,
}: {
  task: Task;
  showProject?: boolean;
  selected?: boolean;
  onSelect?: (checked: boolean) => void;
  /** Adds a trailing Delete button (PM only). */
  onDelete?: () => void;
}) {
  const { t } = usePrefs();
  return (
    <div className={onDelete ? 'task-row has-actions' : 'task-row'} role="row">
      <div className="task-title" role="cell">
        {onSelect && (
          <input
            type="checkbox"
            className="task-check"
            aria-label={t('Select {key}', { key: task.key })}
            checked={!!selected}
            onChange={(e) => onSelect(e.target.checked)}
          />
        )}
        {showProject ? (
          <span className="task-title-stack">
            <Link to={paths.task(task.id)}>
              {task.key} · {task.title}
            </Link>
            {/* A project opens on its Overview first; Backlog and Board are one tab away. */}
            <Link className="proj-link" to={paths.project(task.project_id)}>
              {task.project_name}
            </Link>
          </span>
        ) : (
          <Link to={paths.task(task.id)}>
            {task.key} · {task.title}
          </Link>
        )}
      </div>
      <div className={`cell-status cat-${task.status.category}`} role="cell">
        {t(task.status.name)}
      </div>
      <div className="cell-muted" role="cell">
        {task.due_date ? formatDate(task.due_date) : '—'}
      </div>
      <div className="cell-muted" role="cell">
        {t(PRIORITY_LABEL[task.priority])}
      </div>
      <div className="cell-assignee cell-muted" role="cell">
        {task.assignee ? (
          <>
            <Avatar user={task.assignee} />
            {task.assignee.name}
          </>
        ) : (
          <>
            <span className="avatar unassigned" aria-hidden="true">
              —
            </span>
            {t('Unassigned')}
          </>
        )}
      </div>
      {onDelete && (
        <div className="cell-actions" role="cell">
          <button type="button" className="link-btn task-delete" aria-label={t('Delete {key}', { key: task.key })} onClick={onDelete}>
            {t('Delete')}
          </button>
        </div>
      )}
    </div>
  );
}

/** Column header row of the all-projects task table (Figma "01 PM Task List — Primary"). */
export function TaskTableHead({ withActions }: { withActions?: boolean }) {
  const { t } = usePrefs();
  return (
    <div className={withActions ? 'task-row task-table-head has-actions' : 'task-row task-table-head'} role="row">
      <div role="columnheader">{t('Task / Project')}</div>
      <div role="columnheader">{t('Status')}</div>
      <div role="columnheader">{t('Due date')}</div>
      <div role="columnheader">{t('Priority')}</div>
      <div role="columnheader">{t('Assignee')}</div>
      {withActions && <div role="columnheader" aria-label={t('Actions')} />}
    </div>
  );
}

export function TaskGroup({
  title,
  count,
  countLabel = 'tasks',
  empty,
  selectAll,
  action,
  children,
}: {
  title: string;
  count: number;
  countLabel?: string;
  empty?: string;
  /** Shows the select-all checkbox and collapse chevron in the header (Figma "Board group heading"). */
  selectAll?: { checked: boolean; indeterminate: boolean; onChange: (checked: boolean) => void };
  action?: ReactNode;
  children: ReactNode;
}) {
  const { t } = usePrefs();
  const [open, setOpen] = useState(true);
  return (
    <section className="task-group" role="table" aria-label={t(title)}>
      <div className="task-group-head">
        {selectAll && (
          <>
            <input
              type="checkbox"
              className="task-check"
              aria-label={t('Select all tasks')}
              checked={selectAll.checked}
              ref={(el) => {
                if (el) el.indeterminate = selectAll.indeterminate;
              }}
              onChange={(e) => selectAll.onChange(e.target.checked)}
            />
            <button
              type="button"
              className="group-toggle"
              aria-expanded={open}
              aria-label={t(open ? 'Collapse {title}' : 'Expand {title}', { title: t(title) })}
              onClick={() => setOpen(!open)}
            >
              {open ? '⌄' : '›'}
            </button>
          </>
        )}
        <strong>{t(title)}</strong>
        <span>
          {count} {t(countLabel)}
        </span>
        {action && <div className="task-group-action">{action}</div>}
      </div>
      {!open ? null : count === 0 && empty ? <div className="task-group-empty">{t(empty)}</div> : children}
    </section>
  );
}

/** Remembers every assignee seen so far, so the quick filters stay put while a filter narrows the list. */
function useSeenAssignees(tasks: Task[]) {
  const [seen, setSeen] = useState<UserBrief[]>([]);
  useEffect(() => {
    setSeen((prev) => {
      const known = new Set(prev.map((u) => u.id));
      const added = tasks.flatMap((t) => (t.assignee && !known.has(t.assignee.id) ? [t.assignee] : []));
      return added.length ? [...prev, ...added.filter((u, i, a) => a.findIndex((x) => x.id === u.id) === i)] : prev;
    });
  }, [tasks]);
  return seen;
}

export function TaskFilters({
  filter,
  onChange,
  tasks,
  extra,
  onClear,
}: {
  filter: TaskFilter;
  onChange: (f: TaskFilter) => void;
  tasks: Task[];
  extra?: ReactNode;
  onClear?: () => void;
}) {
  const { t } = usePrefs();
  const assignees = useSeenAssignees(tasks);
  return (
    <div className="task-filters" role="search">
      <input
        type="search"
        className="input search"
        placeholder={t('Search tasks')}
        aria-label={t('Search tasks')}
        value={filter.q}
        onChange={(e) => onChange({ ...filter, q: e.target.value })}
      />
      {extra}
      {assignees.length > 0 && (
        <div className="avatar-filters" role="group" aria-label={t('Filter by assignee')}>
          {assignees.map((u) => (
            <button
              key={u.id}
              type="button"
              className="avatar round"
              style={{ background: colorFor(u.id) }}
              title={u.name}
              aria-label={t('Assignee {name}', { name: u.name })}
              aria-pressed={filter.assigneeId === u.id}
              onClick={() => onChange({ ...filter, assigneeId: filter.assigneeId === u.id ? '' : u.id })}
            >
              {initials(u.name)}
            </button>
          ))}
        </div>
      )}
      <select
        className="input"
        aria-label={t('Filter by status')}
        value={filter.category}
        onChange={(e) => onChange({ ...filter, category: e.target.value as TaskFilter['category'] })}
      >
        <option value="">{t('Status: All')}</option>
        {(Object.keys(CATEGORY_LABEL) as StatusCategory[]).map((c) => (
          <option key={c} value={c}>
            {t(CATEGORY_LABEL[c])}
          </option>
        ))}
      </select>
      <select
        className="input"
        aria-label={t('Filter by priority')}
        value={filter.priority}
        onChange={(e) => onChange({ ...filter, priority: e.target.value as TaskFilter['priority'] })}
      >
        <option value="">{t('Priority: All')}</option>
        {(Object.keys(PRIORITY_LABEL) as TaskPriority[]).map((p) => (
          <option key={p} value={p}>
            {t(PRIORITY_LABEL[p])}
          </option>
        ))}
      </select>
      {onClear && (filter.q.trim() || filter.category || filter.priority || filter.assigneeId) && (
        <button type="button" className="link-btn" onClick={onClear}>
          {t('Clear all')}
        </button>
      )}
    </div>
  );
}
