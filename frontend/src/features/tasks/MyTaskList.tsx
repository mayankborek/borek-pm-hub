import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { addDaysIso, daysOverdue, formatDate, todayIso } from '@/features/projects/projectUi';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { EmptyState } from '@/shared/ui/States';
import { PriorityIndicator } from './PrioritySelect';
import { toneOf } from './StatusSelect';
import type { StatusCategory, Task, TaskPriority } from './tasksApi';
import './myWork.css';

type DueFilter = '' | 'overdue' | 'today' | 'week' | 'later' | 'none';
type GroupBy = '' | 'project' | 'status' | 'priority';

interface MyFilter {
  q: string;
  project: string;
  category: StatusCategory | '';
  priority: TaskPriority | '';
  due: DueFilter;
  group: GroupBy;
}

const CATEGORIES: [StatusCategory, string][] = [
  ['backlog', 'Backlog'],
  ['todo', 'To do'],
  ['in_progress', 'In progress'],
  ['blocked', 'Blocked'],
  ['done', 'Done'],
];
const PRIORITIES: [TaskPriority, string][] = [
  ['critical', 'Critical'],
  ['high', 'High'],
  ['medium', 'Medium'],
  ['low', 'Low'],
];
const DUES: [DueFilter, string][] = [
  ['overdue', 'Overdue'],
  ['today', 'Due today'],
  ['week', 'Due this week'],
  ['later', 'Due later'],
  ['none', 'No due date'],
];
const GROUPS: [GroupBy, string][] = [
  ['', 'No grouping'],
  ['project', 'Project'],
  ['status', 'Status'],
  ['priority', 'Priority'],
];

const isDone = (t: Task) => t.status.category === 'done';
const isOverdue = (t: Task, today: string) => !isDone(t) && !!t.due_date && t.due_date < today;

function matchesDue(t: Task, due: DueFilter, today: string, weekEnd: string) {
  switch (due) {
    case 'overdue':
      return isOverdue(t, today);
    case 'today':
      return !isDone(t) && t.due_date === today;
    case 'week':
      return !isDone(t) && !!t.due_date && t.due_date >= today && t.due_date <= weekEnd;
    case 'later':
      return !isDone(t) && !!t.due_date && t.due_date > weekEnd;
    case 'none':
      return !t.due_date;
    default:
      return true;
  }
}

/** Filters and grouping live in the URL, so a refresh or shared link keeps the view. */
function useMyFilter() {
  const [params, setParams] = useSearchParams();
  const filter: MyFilter = {
    q: params.get('q') ?? '',
    project: params.get('project') ?? '',
    category: (params.get('status') ?? '') as MyFilter['category'],
    priority: (params.get('priority') ?? '') as MyFilter['priority'],
    due: (params.get('due') ?? '') as DueFilter,
    group: (params.get('group') ?? '') as GroupBy,
  };
  const keys: Record<keyof MyFilter, string> = { q: 'q', project: 'project', category: 'status', priority: 'priority', due: 'due', group: 'group' };
  const set = (patch: Partial<MyFilter>) =>
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        (Object.keys(patch) as (keyof MyFilter)[]).forEach((k) => {
          if (patch[k]) p.set(keys[k], patch[k] as string);
          else p.delete(keys[k]);
        });
        return p;
      },
      { replace: true },
    );
  const clear = () => set({ q: '', project: '', category: '', priority: '', due: '' });
  return { filter, set, clear };
}

/** "My Task" list: the developer's assigned tasks, filterable by project, status, priority and due date, with optional grouping. */
export function MyTaskList({ tasks }: { tasks: Task[] }) {
  const { t } = usePrefs();
  const { filter, set, clear } = useMyFilter();
  const today = todayIso();
  const weekEnd = addDaysIso(7);

  const projects = useMemo(() => {
    const seen = new Map<string, string>();
    tasks.forEach((x) => seen.set(x.project_id, x.project_name));
    return [...seen].sort((a, b) => a[1].localeCompare(b[1]));
  }, [tasks]);

  const counts = {
    in_progress: tasks.filter((x) => x.status.category === 'in_progress').length,
    blocked: tasks.filter((x) => x.status.category === 'blocked').length,
    overdue: tasks.filter((x) => isOverdue(x, today)).length,
  };

  const visible = tasks.filter((x) => {
    const q = filter.q.trim().toLowerCase();
    return (
      (!q || x.title.toLowerCase().includes(q) || x.key.toLowerCase().includes(q)) &&
      (!filter.project || x.project_id === filter.project) &&
      (!filter.category || x.status.category === filter.category) &&
      (!filter.priority || x.priority === filter.priority) &&
      matchesDue(x, filter.due, today, weekEnd)
    );
  });

  const groups = useMemo(() => {
    if (!filter.group) return [{ key: 'all', title: '', items: visible }];
    const map = new Map<string, Task[]>();
    visible.forEach((x) => {
      const key = filter.group === 'project' ? x.project_name : filter.group === 'status' ? x.status.name : x.priority;
      map.set(key, [...(map.get(key) ?? []), x]);
    });
    const entries = [...map].map(([key, items]) => ({ key, title: filter.group === 'priority' ? t(PRIORITIES.find((p) => p[0] === key)?.[1] ?? key) : key, items }));
    if (filter.group === 'priority') {
      const order = PRIORITIES.map((p) => p[0] as string);
      return entries.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
    }
    return entries.sort((a, b) => a.title.localeCompare(b.title));
  }, [visible, filter.group, t]);

  const filtered = !!(filter.q.trim() || filter.project || filter.category || filter.priority || filter.due);
  const chip = (label: string, count: number, active: boolean, onClick: () => void, tone: string) => (
    <button type="button" className={`mw-chip ${tone}`} aria-pressed={active} onClick={onClick}>
      {label} <strong>{count}</strong>
    </button>
  );

  return (
    <section className="card mw-card" aria-label={t('My Tasks')}>
      <h3>{t('My Tasks')}</h3>
      <p className="desc">
        {t(visible.length === 1 ? '{n} task' : '{n} tasks', { n: visible.length })}
        {filtered && ` ${t('of {total}', { total: tasks.length })}`}
      </p>

      <div className="mw-chips" role="group" aria-label={t('Quick filters')}>
        {chip(t('In progress'), counts.in_progress, filter.category === 'in_progress', () => set({ category: filter.category === 'in_progress' ? '' : 'in_progress' }), 'progress')}
        {chip(t('Blocked'), counts.blocked, filter.category === 'blocked', () => set({ category: filter.category === 'blocked' ? '' : 'blocked' }), 'blocked')}
        {chip(t('Overdue'), counts.overdue, filter.due === 'overdue', () => set({ due: filter.due === 'overdue' ? '' : 'overdue' }), 'overdue')}
      </div>

      <div className="mw-filters" role="search">
        <input
          type="search"
          className="input search"
          placeholder={t('Search tasks')}
          aria-label={t('Search tasks')}
          value={filter.q}
          onChange={(e) => set({ q: e.target.value })}
        />
        <select className="input" aria-label={t('Filter by project')} value={filter.project} onChange={(e) => set({ project: e.target.value })}>
          <option value="">{t('Project: All')}</option>
          {projects.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
        <select className="input" aria-label={t('Filter by status')} value={filter.category} onChange={(e) => set({ category: e.target.value as MyFilter['category'] })}>
          <option value="">{t('Status: All')}</option>
          {CATEGORIES.map(([v, label]) => (
            <option key={v} value={v}>
              {t(label)}
            </option>
          ))}
        </select>
        <select className="input" aria-label={t('Filter by priority')} value={filter.priority} onChange={(e) => set({ priority: e.target.value as MyFilter['priority'] })}>
          <option value="">{t('Priority: All')}</option>
          {PRIORITIES.map(([v, label]) => (
            <option key={v} value={v}>
              {t(label)}
            </option>
          ))}
        </select>
        <select className="input" aria-label={t('Filter by due date')} value={filter.due} onChange={(e) => set({ due: e.target.value as DueFilter })}>
          <option value="">{t('Due: Any')}</option>
          {DUES.map(([v, label]) => (
            <option key={v} value={v}>
              {t(label)}
            </option>
          ))}
        </select>
        <select className="input" aria-label={t('Group by')} value={filter.group} onChange={(e) => set({ group: e.target.value as GroupBy })}>
          {GROUPS.map(([v, label]) => (
            <option key={v} value={v}>
              {v ? `${t('Group by')}: ${t(label)}` : t(label)}
            </option>
          ))}
        </select>
        {filtered && (
          <button type="button" className="link-btn" onClick={clear}>
            {t('Clear all')}
          </button>
        )}
      </div>

      {visible.length === 0 ? (
        <EmptyState title={t('No matching tasks')} text={t('Try changing or clearing the filters.')} />
      ) : (
        groups.map((g) => (
          <div key={g.key} className="mw-group">
            {g.title && (
              <h4 className="mw-group-title">
                {g.title} <span>{g.items.length}</span>
              </h4>
            )}
            <div className="mw-table-head" aria-hidden="true">
              <span>{t('Task')}</span>
              <span>{t('Status')}</span>
              <span>{t('Priority')}</span>
              <span>{t('Due date')}</span>
            </div>
            <ul className="mw-rows">
              {g.items.map((task) => (
                <TaskLine key={task.id} task={task} today={today} showProject={filter.group !== 'project'} />
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}

function TaskLine({ task, today, showProject }: { task: Task; today: string; showProject: boolean }) {
  const { t } = usePrefs();
  const late = isOverdue(task, today);
  const days = daysOverdue(task.due_date, today);
  return (
    <li>
      <span className="mw-title">
        <Link to={paths.task(task.id)}>
          {task.key} · {task.title}
        </Link>
        {showProject && <span className="mw-sub">{task.project_name}</span>}
      </span>
      <span className={`ss-label tone-${toneOf(task.status)}`}>{task.status.name}</span>
      <PriorityIndicator priority={task.priority} />
      <span className={late ? 'mw-due late' : 'mw-due'}>
        {formatDate(task.due_date)}
        {late && <em>{days === 1 ? t('1 day overdue') : t('{n} days overdue', { n: days })}</em>}
      </span>
    </li>
  );
}
