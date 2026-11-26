import { useMemo, useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState } from '@/shared/ui/States';
import { useProjectContext } from '@/features/projects/ProjectLayout';
import { emptyFilter, useProjectMembers, useProjectStatuses, useProjectTasks, type StatusCategory, type Task, type TaskPriority } from '@/features/tasks/tasksApi';
import { PRIORITIES, PRIORITY_COLOR, PRIORITY_LABEL } from '@/features/accountManager/amWork';
import { PriorityMark } from './devUi';

const BAR_AREA = 200; // 176 px of bars plus room for the count above the tallest one
const BAR_COLOR: Record<string, string> = { 'to do': '#828796', 'in progress': '#4573DB', 'code review': '#7A52BF', blocked: '#BF3B3B', testing: '#E07E00', done: '#17735E' };
const CATEGORY_BAR: Record<StatusCategory, string> = { backlog: '#828796', todo: '#828796', in_progress: '#4573DB', blocked: '#BF3B3B', done: '#17735E' };
const barColor = (name: string, category: StatusCategory) => BAR_COLOR[name.toLowerCase()] ?? CATEGORY_BAR[category];

function dueThisWeek(tasks: Task[]) {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return tasks.filter((x) => {
    if (!x.due_date || x.status.category === 'done') return false;
    const d = new Date(`${x.due_date}T00:00:00`);
    return d >= start && d < end;
  }).length;
}

/** Overview tab (borek-flow-screens): four metric cards, Tasks by status and Tasks by priority. */
export function DevOverviewPage() {
  const { t } = usePrefs();
  const project = useProjectContext();
  const { data, isPending, isError, refetch } = useProjectTasks(project.id, emptyFilter);
  const { data: statuses } = useProjectStatuses(project.id);
  const { data: members } = useProjectMembers(project.id);
  const [showDone, setShowDone] = useState(false);

  const stats = useMemo(() => {
    const tasks = data?.items ?? [];
    const total = data?.total ?? tasks.length;
    const done = tasks.filter((x) => x.status.category === 'done').length;
    // Workflow order from the project's statuses; a status seen only on a task is appended. Backlog is not part of the overview.
    const slices = new Map<string, { name: string; color: string; count: number }>();
    (statuses ?? []).filter((s) => s.category !== 'backlog').forEach((s) => slices.set(s.name, { name: s.name, color: barColor(s.name, s.category), count: 0 }));
    tasks.filter((x) => x.status.category !== 'backlog').forEach((x) => {
      const s = slices.get(x.status.name) ?? { name: x.status.name, color: barColor(x.status.name, x.status.category), count: 0 };
      s.count += 1;
      slices.set(x.status.name, s);
    });
    const byPriority = PRIORITIES.map((p) => ({ key: p as TaskPriority, count: tasks.filter((x) => x.priority === p).length }));
    return {
      total,
      done,
      open: total - done,
      percent: total ? Math.round((done / total) * 100) : 0,
      due: dueThisWeek(tasks),
      slices: [...slices.values()],
      byPriority,
      maxPriority: Math.max(5, ...byPriority.map((p) => p.count)),
    };
  }, [data, statuses]);

  if (isPending)
    return (
      <section className="dv-loading" aria-busy="true">
        <h3>{t('Loading project overview...')}</h3>
        <p>{t('Project progress, tasks, milestones and team details will appear when ready.')}</p>
        <i /><i /><i />
      </section>
    );
  if (isError) return <ErrorState title="We couldn’t load the overview" text="Check your connection and try again." onRetry={() => void refetch()} />;

  const metrics = [
    { label: t('Open task'), value: stats.open, note: t('{n} due this week', { n: stats.due }) },
    { label: t('Progress'), value: `${stats.percent}%`, note: t('{done} of {total} tasks complete', { done: stats.done, total: stats.total }) },
    { label: t('Done'), value: stats.done, note: t('Completed tasks') },
    { label: t('Team Members'), value: members?.length ?? '—', note: t('Assigned to this project') },
  ];
  const visible = stats.slices.filter((s) => showDone || s.name.toLowerCase() !== 'done');
  const active = stats.slices.filter((s) => s.name.toLowerCase() !== 'done').reduce((n, s) => n + s.count, 0);
  const barMax = Math.max(1, ...visible.map((s) => s.count));
  const axisMax = Math.ceil(stats.maxPriority / 5) * 5;
  const ticks = [axisMax, (axisMax * 2) / 3, axisMax / 3, 0].map(Math.round);

  return (
    <>
      <div className="dv-metrics">
        {metrics.map((m) => (
          <section key={m.label} aria-label={m.label}>
            <span>{m.label}</span>
            <strong>{m.value}</strong>
            <small>{m.note}</small>
          </section>
        ))}
      </div>

      <div className="dv-charts">
        <section aria-label={t('Tasks by status')}>
          <h3>{t('Tasks by status')}</h3>
          <div className="dv-sub">
            <span>{t('{active} active tasks · {done} done', { active, done: stats.done })}</span>
            <label>
              <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} />
              {t('Done')}
            </label>
          </div>
          <div className="dv-bars" role="img" aria-label={t('{n} tasks by status', { n: stats.total })}>
            {visible.map((s) => (
              <div key={s.name}>
                <span>{t(s.name)}</span>
                <i><b style={{ width: `${(s.count / barMax) * 100}%`, background: s.color }} /></i>
                <em>{s.count}</em>
              </div>
            ))}
          </div>
        </section>

        <section aria-label={t('Tasks by priority')}>
          <h3>{t('Tasks by priority')}</h3>
          <p className="dv-desc">{t('How the project’s {n} tasks are prioritized.', { n: stats.total })}</p>
          <div className="dv-pchart">
            <div className="dv-axis" style={{ height: BAR_AREA - 24 }} aria-hidden="true">
              {ticks.map((tick) => <span key={tick}>{tick}</span>)}
            </div>
            <div className="dv-pcols">
              {stats.byPriority.map((p) => (
                <div key={p.key}>
                  <div className="dv-pbar" style={{ height: BAR_AREA }}>
                    <strong>{p.count}</strong>
                    <i style={{ height: p.count ? (p.count / axisMax) * (BAR_AREA - 24) : 1, background: p.count ? PRIORITY_COLOR[p.key] : 'var(--bf-line)' }} />
                  </div>
                  <span><PriorityMark priority={p.key} label={false} />{t(PRIORITY_LABEL[p.key])}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
