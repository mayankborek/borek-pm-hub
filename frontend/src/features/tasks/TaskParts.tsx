import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { formatDate } from '@/features/projects/projectUi';
import type { StatusCategory, Task, TaskFilter, TaskPriority, UserBrief } from './tasksApi';
import './tasks.css';

const AVATAR_COLORS = ['#4f3db8', '#218c6e', '#f59421', '#c94a32', '#1d6fa5'];
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
}: {
  task: Task;
  showProject?: boolean;
  selected?: boolean;
  onSelect?: (checked: boolean) => void;
}) {
  return (
    <div className="task-row" role="row">
      <div className="task-title" role="cell">
        {onSelect && (
          <input
            type="checkbox"
            className="task-check"
            aria-label={`Select ${task.key}`}
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
        {task.status.name}
      </div>
      <div className="cell-muted" role="cell">
        {task.due_date ? formatDate(task.due_date) : '—'}
      </div>
      <div className="cell-muted" role="cell">
        {PRIORITY_LABEL[task.priority]}
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
            Unassigned
          </>
        )}
      </div>
    </div>
  );
}

/** Column header row of the all-projects task table (Figma "01 PM Task List — Primary"). */
export function TaskTableHead() {
  return (
    <div className="task-row task-table-head" role="row">
      <div role="columnheader">Task / Project</div>
      <div role="columnheader">Status</div>
      <div role="columnheader">Due date</div>
      <div role="columnheader">Priority</div>
      <div role="columnheader">Assignee</div>
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
  const [open, setOpen] = useState(true);
  return (
    <section className="task-group" role="table" aria-label={title}>
      <div className="task-group-head">
        {selectAll && (
          <>
            <input
              type="checkbox"
              className="task-check"
              aria-label="Select all tasks"
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
              aria-label={open ? `Collapse ${title}` : `Expand ${title}`}
              onClick={() => setOpen(!open)}
            >
              {open ? '⌄' : '›'}
            </button>
          </>
        )}
        <strong>{title}</strong>
        <span>
          {count} {countLabel}
        </span>
        {action && <div className="task-group-action">{action}</div>}
      </div>
      {!open ? null : count === 0 && empty ? <div className="task-group-empty">{empty}</div> : children}
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
}: {
  filter: TaskFilter;
  onChange: (f: TaskFilter) => void;
  tasks: Task[];
  extra?: ReactNode;
}) {
  const assignees = useSeenAssignees(tasks);
  return (
    <div className="task-filters" role="search">
      <input
        type="search"
        className="input search"
        placeholder="Search tasks"
        aria-label="Search tasks"
        value={filter.q}
        onChange={(e) => onChange({ ...filter, q: e.target.value })}
      />
      {extra}
      {assignees.length > 0 && (
        <div className="avatar-filters" role="group" aria-label="Filter by assignee">
          {assignees.map((u) => (
            <button
              key={u.id}
              type="button"
              className="avatar round"
              style={{ background: colorFor(u.id) }}
              title={u.name}
              aria-label={`Assignee ${u.name}`}
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
        aria-label="Filter by status"
        value={filter.category}
        onChange={(e) => onChange({ ...filter, category: e.target.value as TaskFilter['category'] })}
      >
        <option value="">Status: All</option>
        {(Object.keys(CATEGORY_LABEL) as StatusCategory[]).map((c) => (
          <option key={c} value={c}>
            {CATEGORY_LABEL[c]}
          </option>
        ))}
      </select>
      <select
        className="input"
        aria-label="Filter by priority"
        value={filter.priority}
        onChange={(e) => onChange({ ...filter, priority: e.target.value as TaskFilter['priority'] })}
      >
        <option value="">Priority: All</option>
        {(Object.keys(PRIORITY_LABEL) as TaskPriority[]).map((p) => (
          <option key={p} value={p}>
            {PRIORITY_LABEL[p]}
          </option>
        ))}
      </select>
    </div>
  );
}
