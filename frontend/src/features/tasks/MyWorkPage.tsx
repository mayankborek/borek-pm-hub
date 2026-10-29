import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { addDaysIso, daysOverdue, formatDate, todayIso } from '@/features/projects/projectUi';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Pill } from '@/shared/ui/Pill';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import '@/features/dashboard/dashboard.css';
import { useMyDashboard, useMyTasks, type MyDashboard } from './myWorkApi';
import { PriorityIndicator } from './PrioritySelect';
import { toneOf } from './StatusSelect';
import type { Task } from './tasksApi';
import './taskDetail.css';

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? 'Good Morning' : h < 18 ? 'Good Afternoon' : 'Good Evening';
};

const isOpen = (t: Task) => t.status.category !== 'done';

/** Developer landing page (Figma "02 My Work"): GET /dashboard/me for counts and attention items, GET /me/tasks for the list. */
export function MyWorkPage() {
  const { user } = useAuth();
  const { t } = usePrefs();
  const dashboard = useMyDashboard();
  const tasks = useMyTasks();
  const firstName = user?.name.split(' ')[0] ?? '';

  const failed = dashboard.isError || tasks.isError;
  const loading = dashboard.isPending || tasks.isPending;

  return (
    <section className="page-body dashboard">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            {t(greeting())}, {firstName}
          </h1>
          <p className="page-desc">{t('Your assigned work, upcoming deadlines, and tasks that need attention.')}</p>
        </div>
      </div>

      {loading ? (
        <LoadingState title={t('Loading your work')} text={t('Fetching your assigned tasks and items that need attention.')} />
      ) : failed ? (
        <ErrorState
          title={t('We couldn’t load your work')}
          text={t('Check your connection and try again.')}
          onRetry={() => {
            void dashboard.refetch();
            void tasks.refetch();
          }}
        />
      ) : (
        <MyWorkBody dashboard={dashboard.data} tasks={tasks.data.items} />
      )}
    </section>
  );
}

function MyWorkBody({ dashboard, tasks }: { dashboard: MyDashboard; tasks: Task[] }) {
  const { t } = usePrefs();
  const today = todayIso();
  const weekEnd = addDaysIso(7);
  const { summary, projects } = dashboard;

  const dueThisWeek = tasks.filter((x) => isOpen(x) && !!x.due_date && x.due_date >= today && x.due_date <= weekEnd);
  const dueToday = dueThisWeek.filter((x) => x.due_date === today).length;
  const metrics = [
    {
      label: t('Assigned Tasks'),
      value: summary.total,
      note: t('{c} completed · {p} projects', { c: summary.completed, p: projects.length }),
    },
    { label: t('Tasks in Progress'), value: summary.in_progress, note: t('{n} active tasks', { n: summary.total - summary.completed }) },
    { label: t('Due this Week'), value: dueThisWeek.length, note: t('{n} due today', { n: dueToday }) },
    { label: t('Overdue Tasks'), value: summary.overdue, note: t('Needs your attention') },
  ];

  return (
    <>
      <section className="metrics" aria-label={t('Metrics overview')}>
        {metrics.map((m) => (
          <article className="metric" key={m.label}>
            <h3>{m.label}</h3>
            <strong>{m.value}</strong>
            <span>{m.note}</span>
          </article>
        ))}
      </section>

      <div className="split">
        <AssignedTasks tasks={tasks} projectCount={projects.length} />

        <AttentionAreas dashboard={dashboard} today={today} />
      </div>
    </>
  );
}

function AssignedTasks({ tasks, projectCount }: { tasks: Task[]; projectCount: number }) {
  const { t } = usePrefs();
  return (
    <section className="card" aria-label={t('All Assigned Tasks')}>
      <h3>{t('All Assigned Tasks')}</h3>
      <p className="desc">{t(tasks.length === 1 ? '{n} task assigned to you across {p} projects' : '{n} tasks assigned to you across {p} projects', { n: tasks.length, p: projectCount })}</p>
      {tasks.length > 0 && !tasks.some(isOpen) && <p className="muted">{t('No active tasks right now. Your completed work is listed below.')}</p>}
      <div className="mw-head" aria-hidden="true">
        <span>{t('Task')}</span>
        <span>{t('Status')}</span>
        <span>{t('Priority')}</span>
      </div>
      {tasks.length === 0 ? (
        <EmptyState title={t('No tasks assigned')} text={t('Tasks assigned to you will appear here. Ask your Project Manager if you expected some.')} />
      ) : (
        <ul className="mw-list">
          {tasks.map((task) => (
            <li key={task.id}>
              <Link to={paths.task(task.id)}>
                {task.key} · {task.title} →
              </Link>
              <span className={`ss-label tone-${toneOf(task.status)}`}>{task.status.name}</span>
              <PriorityIndicator priority={task.priority} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AttentionAreas({ dashboard, today }: { dashboard: MyDashboard; today: string }) {
  const { t } = usePrefs();
  const overdueIds = new Set(dashboard.overdue.items.map((x) => x.id));
  const items: { task: Task; kind: 'overdue' | 'blocked' }[] = [
    ...dashboard.overdue.items.map((task) => ({ task, kind: 'overdue' as const })),
    ...dashboard.blocked.items.filter((x) => !overdueIds.has(x.id)).map((task) => ({ task, kind: 'blocked' as const })),
  ].slice(0, 6);

  const meta = (task: Task, kind: 'overdue' | 'blocked') => {
    if (kind === 'overdue') {
      const d = daysOverdue(task.due_date, today);
      return `${formatDate(task.due_date)} · ${d === 1 ? t('1 day overdue') : t('{n} days overdue', { n: d })}`;
    }
    const days = task.blocked_at ? daysOverdue(task.blocked_at.slice(0, 10), today) : 0;
    return days > 0 ? t(days === 1 ? 'blocked for {n} day' : 'blocked for {n} days', { n: days }) : t('blocked');
  };

  return (
    <section className="card" aria-label={t('Attention Areas')}>
      <h3>{t('Attention Areas')}</h3>
      {items.length === 0 ? (
        <p className="muted attn-note">{t('Nothing is blocked or overdue. Nice work.')}</p>
      ) : (
        <ul className="attn-list">
          {items.map(({ task, kind }) => (
            <li key={task.id}>
              <Link to={paths.task(task.id)} className={kind === 'overdue' ? 'attn-title warn' : 'attn-title err'}>
                {task.key} · {task.title}
              </Link>
              <div className="attn-meta">
                <span>
                  {task.project_name} · {meta(task, kind)}
                </span>
                <Pill tone={kind === 'overdue' ? 'overdue' : 'blocked'}>{kind === 'overdue' ? t('Overdue') : t('Blocked')}</Pill>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
