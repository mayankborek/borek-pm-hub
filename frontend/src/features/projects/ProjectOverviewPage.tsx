import { useMemo } from 'react';
import { emptyFilter, useProjectMembers, useProjectStatuses, useProjectTasks } from '@/features/tasks/tasksApi';
import type { StatusCategory, Task, TaskPriority } from '@/features/tasks/tasksApi';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useProjectContext } from './ProjectLayout';
import highestIcon from './assets/priority-highest.svg';
import highIcon from './assets/priority-high.svg';
import mediumIcon from './assets/priority-medium.svg';
import lowIcon from './assets/priority-low.svg';
import lowestIcon from './assets/priority-lowest.svg';
import './projects.css';

const CATEGORY_COLOR: Record<StatusCategory, string> = {
  backlog: 'var(--surface-2)',
  todo: 'var(--surface-2)',
  in_progress: '#4388ee',
  blocked: '#d99a27',
  done: '#64ad69',
};
/** Named workflow states keep the design's colours; anything else falls back to its category colour. */
const NAME_COLOR: Record<string, string> = { 'code review': '#7c55ce', testing: '#24a49a' };

const PRIORITIES: { key: TaskPriority; label: string; icon: string; color: string }[] = [
  { key: 'highest', label: 'Highest', icon: highestIcon, color: '#c94a32' },
  { key: 'high', label: 'High', icon: highIcon, color: '#c94a32' },
  { key: 'medium', label: 'Medium', icon: mediumIcon, color: '#e07e00' },
  { key: 'low', label: 'Low', icon: lowIcon, color: '#2e61d6' },
  { key: 'lowest', label: 'Lowest', icon: lowestIcon, color: '#7a8aa8' },
];

const DONUT_SIZE = 220;
const DONUT_STROKE = 36;
const BAR_AREA = 184;

const colorOf = (name: string, category: StatusCategory) => NAME_COLOR[name.toLowerCase()] ?? CATEGORY_COLOR[category];

function dueThisWeek(tasks: Task[]) {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return tasks.filter((t) => {
    if (!t.due_date || t.status.category === 'done') return false;
    const d = new Date(`${t.due_date}T00:00:00`);
    return d >= start && d < end;
  }).length;
}

function Donut({ slices, total }: { slices: { name: string; color: string; count: number }[]; total: number }) {
  const { t } = usePrefs();
  const r = (DONUT_SIZE - DONUT_STROKE) / 2;
  const circ = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="donut" role="img" aria-label={t('{n} tasks by status', { n: total })}>
      <svg width={DONUT_SIZE} height={DONUT_SIZE} viewBox={`0 0 ${DONUT_SIZE} ${DONUT_SIZE}`}>
        <g transform={`rotate(-90 ${DONUT_SIZE / 2} ${DONUT_SIZE / 2})`} fill="none" strokeWidth={DONUT_STROKE}>
          <circle cx={DONUT_SIZE / 2} cy={DONUT_SIZE / 2} r={r} stroke="var(--surface-2)" />
          {total > 0 &&
            slices
              .filter((s) => s.count > 0)
              .map((s) => {
                const len = (s.count / total) * circ;
                const el = (
                  <circle
                    key={s.name}
                    cx={DONUT_SIZE / 2}
                    cy={DONUT_SIZE / 2}
                    r={r}
                    stroke={s.color}
                    strokeDasharray={`${len} ${circ - len}`}
                    strokeDashoffset={-offset}
                  />
                );
                offset += len;
                return el;
              })}
        </g>
      </svg>
      <div className="donut-total">
        <strong>{total}</strong>
        <span>{t('Total tasks')}</span>
      </div>
    </div>
  );
}

export function ProjectOverviewPage() {
  const { t } = usePrefs();
  const project = useProjectContext();
  const { data, isPending, isError, refetch } = useProjectTasks(project.id, emptyFilter);
  const { data: statuses } = useProjectStatuses(project.id);
  const { data: members } = useProjectMembers(project.id);

  const stats = useMemo(() => {
    const tasks = data?.items ?? [];
    const total = data?.total ?? tasks.length;
    const done = tasks.filter((t) => t.status.category === 'done').length;

    // Workflow order from the project's statuses; any status seen on a task but missing from that list is appended.
    const slices = new Map<string, { name: string; color: string; count: number }>();
    // Backlog tasks are not part of the status overview.
    (statuses ?? [])
      .filter((s) => s.category !== 'backlog')
      .forEach((s) => slices.set(s.name, { name: s.name, color: colorOf(s.name, s.category), count: 0 }));
    tasks.filter((t) => t.status.category !== 'backlog').forEach((t) => {
      const s = slices.get(t.status.name) ?? { name: t.status.name, color: colorOf(t.status.name, t.status.category), count: 0 };
      s.count += 1;
      slices.set(t.status.name, s);
    });

    const byPriority = PRIORITIES.map((p) => ({ ...p, count: tasks.filter((t) => t.priority === p.key).length }));
    return {
      total,
      done,
      open: total - done,
      percent: total ? Math.round((done / total) * 100) : 0,
      due: dueThisWeek(tasks),
      slices: [...slices.values()],
      statusTotal: [...slices.values()].reduce((n, s) => n + s.count, 0),
      byPriority,
      maxPriority: Math.max(5, ...byPriority.map((p) => p.count)),
    };
  }, [data, statuses]);

  if (isPending) return <LoadingState title="Loading overview" text="Fetching this project’s tasks." />;
  if (isError)
    return <ErrorState title="We couldn’t load the overview" text="Check your connection and try again." onRetry={() => void refetch()} />;

  const metrics = [
    { label: t('Open tasks'), value: stats.open, note: t('{n} due this week', { n: stats.due }) },
    { label: t('Progress'), value: `${stats.percent}%`, note: t('{done} of {total} tasks complete', { done: stats.done, total: stats.total }) },
    { label: t('Done'), value: stats.done, note: t('Completed tasks') },
    { label: t('Team members'), value: members?.length ?? '—', note: t('Assigned to this project') },
  ];
  const axisMax = Math.ceil(stats.maxPriority / 5) * 5;
  const ticks = [axisMax, (axisMax * 2) / 3, axisMax / 3, 0].map(Math.round);

  return (
    <div className="ov">
      <div className="ov-metrics">
        {metrics.map((m) => (
          <section className="ov-metric" key={m.label} aria-label={m.label}>
            <span className="ov-metric-label">{m.label}</span>
            <strong>{m.value}</strong>
            <span className="ov-metric-note">{m.note}</span>
          </section>
        ))}
      </div>

      <div className="ov-charts">
        <section className="ov-card" aria-label={t('Status overview')}>
          <h3>{t('Status overview')}</h3>
          <p className="ov-desc">{t('A snapshot of all {n} tasks in this project.', { n: stats.statusTotal })}</p>
          <div className="ov-status">
            <Donut slices={stats.slices} total={stats.statusTotal} />
            <ul className="legend">
              {stats.slices.map((s) => (
                <li key={s.name}>
                  <i style={{ background: s.color }} />
                  <span>{t(s.name)}</span>
                  <strong>{s.count}</strong>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="ov-card" aria-label={t('Priority breakdown')}>
          <h3>{t('Priority breakdown')}</h3>
          <p className="ov-desc">{t('How the project’s {n} tasks are prioritized.', { n: stats.total })}</p>
          <div className="pchart">
            <div className="pchart-axis" style={{ height: BAR_AREA }} aria-hidden="true">
              {ticks.map((tick) => (
                <span key={tick}>{tick}</span>
              ))}
            </div>
            <div className="pchart-cols">
              {stats.byPriority.map((p) => (
                <div className="pcol" key={p.key}>
                  <div className="pcol-bar" style={{ height: BAR_AREA }}>
                    <strong>{p.count}</strong>
                    <i style={{ height: p.count ? (p.count / axisMax) * (BAR_AREA - 24) : 1, background: p.count ? p.color : 'var(--line)' }} />
                  </div>
                  <span className="pcol-label">
                    <img src={p.icon} alt="" width={16} height={16} />
                    {t(p.label)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
