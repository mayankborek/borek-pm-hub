import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { emptyFilter, useProjectMembers, useProjectStatuses, useProjectTasks } from '@/features/tasks/tasksApi';
import type { StatusCategory, Task, TaskPriority } from '@/features/tasks/tasksApi';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { nextMilestone, useRoadmap } from '@/features/milestones/milestonesApi';
import { useProjectContext } from './ProjectLayout';
import { formatDate } from './projectUi';
import highestIcon from './assets/priority-highest.svg';
import highIcon from './assets/priority-high.svg';
import mediumIcon from './assets/priority-medium.svg';
import lowIcon from './assets/priority-low.svg';
import lowestIcon from './assets/priority-lowest.svg';
import './projects.css';

const CATEGORY_COLOR: Record<StatusCategory, string> = {
  backlog: '#868a9e',
  todo: '#868a9e',
  in_progress: '#3b6bdb',
  blocked: '#c43d3d',
  done: '#1b7f4f',
};
/** Named workflow states keep the design's colours; anything else falls back to its category colour. */
const NAME_COLOR: Record<string, string> = { 'code review': '#7b4fc4', testing: '#e07b00' };

const PRIORITIES: { key: TaskPriority; label: string; icon: string; color: string }[] = [
  { key: 'highest', label: 'Highest', icon: highestIcon, color: '#c94a32' },
  { key: 'high', label: 'High', icon: highIcon, color: '#c94a32' },
  { key: 'medium', label: 'Medium', icon: mediumIcon, color: '#e07e00' },
  { key: 'low', label: 'Low', icon: lowIcon, color: '#2e61d6' },
  { key: 'lowest', label: 'Lowest', icon: lowestIcon, color: '#7a8aa8' },
];

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

export function ProjectOverviewPage() {
  const { t } = usePrefs();
  const project = useProjectContext();
  const isPm = useAuth().user?.role === 'pm';
  const { data, isPending, isError, refetch } = useProjectTasks(project.id, emptyFilter);
  const { data: statuses } = useProjectStatuses(project.id);
  const { data: members } = useProjectMembers(project.id);
  const [showDone, setShowDone] = useState(false);
  const next = nextMilestone(useRoadmap(project.id).data);

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

    const blocked = tasks.filter((t) => t.status.category === 'blocked').length;
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
      blocked,
      maxPriority: Math.max(5, ...byPriority.map((p) => p.count)),
    };
  }, [data, statuses]);

  if (isPending) return <LoadingState title="Loading overview" text="Fetching this project’s tasks." />;
  if (isError)
    return <ErrorState title="We couldn’t load the overview" text="Check your connection and try again." onRetry={() => void refetch()} />;

  const metrics = [
    { label: t('Open tasks'), value: stats.open, note: t('{n} due this week', { n: stats.due }) },
    { label: t('Progress'), value: `${stats.percent}%`, note: t('{done} of {total} tasks complete', { done: stats.done, total: stats.total }) },
    { label: t('Completed'), value: stats.done, note: t('Completed tasks') },
    { label: t('Team members'), value: members?.length ?? '—', note: t('Assigned to this project') },
  ];
  const axisMax = Math.ceil(stats.maxPriority / 5) * 5;
  const ticks = [axisMax, (axisMax * 2) / 3, axisMax / 3, 0].map(Math.round);

  const visible = stats.slices.filter((s) => showDone || s.name.toLowerCase() !== 'done');
  const activeTotal = stats.slices.filter((s) => s.name.toLowerCase() !== 'done').reduce((n, s) => n + s.count, 0);
  const barMax = Math.max(1, ...visible.map((s) => s.count));
  const target = project.target_end_date ? new Date(`${project.target_end_date}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : t('Not set');

  return (
    <div className="ov">
      <div className="ov-metrics">
        {metrics.map((m, i) => (
          <section className="ov-metric" key={m.label} aria-label={m.label}>
            <span className={i === 2 ? 'ov-metric-label good' : 'ov-metric-label'}>{m.label}</span>
            <strong>{m.value}</strong>
            <span className="ov-metric-note">{m.note}</span>
          </section>
        ))}
      </div>

      <div className="ov-alerts">
        <section className="ov-alert" aria-label={t('Next milestone')}>
          <div>
            <b>{t('Next milestone')}</b>
            <span>{next ? `${next.name} · ${formatDate(next.due_date)}` : target}</span>
          </div>
          {isPm && <Link to={paths.projectMilestones(project.id)}>{t('View milestones')}</Link>}
        </section>
        <section className="ov-alert" aria-label={t('Blockers')}>
          <div>
            {stats.blocked > 0 ? (
              <>
                <b className="red">{t(stats.blocked === 1 ? '{n} blocker needs attention' : '{n} blockers need attention', { n: stats.blocked })}</b>
                <span>{t('Review linked work before confirming delivery.')}</span>
              </>
            ) : (
              <>
                <b>{t('No blockers')}</b>
                <span>{t('Nothing is blocked right now.')}</span>
              </>
            )}
          </div>
          {stats.blocked > 0 && <Link to={paths.projectBoard(project.id)}>{t('Review blocker')}</Link>}
        </section>
      </div>

      <div className="ov-charts">
        <section className="ov-card" aria-label={t('Tasks by status')}>
          <h3>{t('Tasks by status')}</h3>
          <div className="ov-sub">
            <span>{t('{active} active tasks · {done} done', { active: activeTotal, done: stats.done })}</span>
            <label className="ov-check">
              <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} />
              {t('Done')}
            </label>
          </div>
          <div className="sbars" role="img" aria-label={t('{n} tasks by status', { n: stats.statusTotal })}>
            {visible.map((s) => (
              <div className="sbar" key={s.name}>
                <span>{t(s.name)}</span>
                <div className="sbar-track">
                  <i style={{ width: `${(s.count / barMax) * 100}%`, background: s.color }} />
                </div>
                <b>{s.count}</b>
              </div>
            ))}
          </div>
        </section>

        <section className="ov-card" aria-label={t('Tasks by priority')}>
          <h3>{t('Tasks by priority')}</h3>
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
