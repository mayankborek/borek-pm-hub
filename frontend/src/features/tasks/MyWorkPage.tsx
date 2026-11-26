import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { addDaysIso, daysOverdue, todayIso } from '@/features/projects/projectUi';
import { fmtDate } from '@/features/developer/devUi';
import { PRIORITY_LABEL } from '@/features/accountManager/amWork';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import '@/features/developer/developer.css';
import { useMyDashboard, useMyTasks, type MyDashboard } from './myWorkApi';
import type { Task } from './tasksApi';

const FOCUS_SIZE = 4;
const ATTENTION_SIZE = 6;

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
};

const isOpen = (x: Task) => x.status.category !== 'done';
const isOverdue = (x: Task, today: string) => isOpen(x) && !!x.due_date && x.due_date < today;
const isHot = (x: Task) => x.priority === 'highest' || x.priority === 'high';

/** Soonest due first; tasks without a due date go last. */
const byDue = (a: Task, b: Task) => (a.due_date ?? '9999-12-31').localeCompare(b.due_date ?? '9999-12-31');

const Open = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M2.5 9.5l7-7M3.5 2.5h6v6" />
  </svg>
);

const STAT_ICONS = {
  folder: <path d="M1.5 3.5A1.5 1.5 0 0 1 3 2h2.7l1.6 2.4H13A1.5 1.5 0 0 1 14.5 6v6A1.5 1.5 0 0 1 13 13.5H3A1.5 1.5 0 0 1 1.5 12z" />,
  layers: <path d="M1.5 8 8 11.7 14.5 8M1.5 11 8 14.7 14.5 11M8 1.5 14.5 5.2 8 8.9 1.5 5.2z" />,
  calendar: <path d="M5.5 1.5v3M10.5 1.5v3M2 6.5h12M3.5 3h9A1.5 1.5 0 0 1 14 4.5v8a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12.5v-8A1.5 1.5 0 0 1 3.5 3zM5 10h1.5M9.5 10H11" />,
  clock: <path d="M8 4.5V8l2.2 1.5M14 8A6 6 0 1 1 2 8a6 6 0 0 1 12 0z" />,
};

/** Developer landing page (borek-flow-my-work): four summary cards, My Focus and Needs Attention. */
export function MyWorkPage() {
  const { user } = useAuth();
  const { t } = usePrefs();
  const dashboard = useMyDashboard();
  const tasks = useMyTasks();
  const firstName = user?.name.split(' ')[0] ?? '';

  const failed = dashboard.isError || tasks.isError;
  const loading = dashboard.isPending || tasks.isPending;

  return (
    <section className="dv-mywork">
      <h2 className="dv-mw-title">{t(greeting())}, {firstName}</h2>
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
  const { summary } = dashboard;
  const active = summary.total - summary.completed;

  const open = tasks.filter(isOpen);
  const dueThisWeek = open.filter((x) => !!x.due_date && x.due_date >= today && x.due_date <= weekEnd);
  const dueToday = dueThisWeek.filter((x) => x.due_date === today).length;

  const metrics = [
    { label: t('Assigned Tasks'), value: summary.total, note: t('{a} active · {c} completed', { a: active, c: summary.completed }), icon: 'folder' as const, tone: 'blue' },
    { label: t('Tasks in Progress'), value: summary.in_progress, note: t('{n} active tasks', { n: active }), icon: 'layers' as const, tone: 'green' },
    { label: t('Due This Week'), value: dueThisWeek.length, note: t('{n} due today', { n: dueToday }), icon: 'calendar' as const, tone: 'amber' },
    { label: t('Overdue Tasks'), value: summary.overdue, note: t('Needs your attention'), icon: 'clock' as const, tone: 'red' },
  ];

  // Focus: what is being worked on or stuck, soonest due first; falls back to any open task.
  const working = open.filter((x) => x.status.category === 'in_progress' || x.status.category === 'blocked');
  const focus = [...(working.length ? working : open)].sort(byDue).slice(0, FOCUS_SIZE);

  return (
    <>
      <section className="dv-mw-stats" aria-label={t('Task summary')}>
        {metrics.map((m) => (
          <article key={m.label}>
            <h2>{m.label}</h2>
            <p className="num">{m.value}</p>
            <p className="muted">{m.note}</p>
            <span className={`ico ${m.tone}`}>
              <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{STAT_ICONS[m.icon]}</svg>
            </span>
          </article>
        ))}
      </section>

      <div className="dv-mw-panels">
        <FocusPanel tasks={focus} today={today} />
        <AttentionPanel dashboard={dashboard} today={today} />
      </div>
    </>
  );
}

function FocusPanel({ tasks, today }: { tasks: Task[]; today: string }) {
  const { t } = usePrefs();
  return (
    <section className="dv-mw-panel" aria-label={t('My Focus')}>
      <div className="head">
        <h2>{t('My Focus')}</h2>
        <span className="count">{t(tasks.length === 1 ? '{n} task' : '{n} tasks', { n: tasks.length })}</span>
      </div>
      {tasks.length === 0 ? (
        <EmptyState title={t('No tasks assigned')} text={t('Tasks assigned to you will appear here. Ask your Project Manager if you expected some.')} />
      ) : (
        <ul>
          {tasks.map((x) => {
            const blocked = x.status.category === 'blocked';
            return (
              <li className="row" key={x.id}>
                <div>
                  <h3>{x.title}</h3>
                  <p className="muted">{x.key} · {x.project_name}</p>
                </div>
                <div className="badges">
                  <span className={blocked ? 'badge red wide' : 'badge blue'}>{x.status.name}</span>
                  {isOverdue(x, today) && <span className="badge red">{t('Overdue')}</span>}
                </div>
                <strong className={isHot(x) ? 'prio' : 'prio low'}>{t(PRIORITY_LABEL[x.priority])}</strong>
                {x.due_date ? <time className="muted" dateTime={x.due_date}>{fmtDate(x.due_date)}</time> : <span className="muted">{t('No due date')}</span>}
                <Link className="open" to={paths.task(x.id)} aria-label={t('Open {title}', { title: x.title })}><Open /></Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function AttentionPanel({ dashboard, today }: { dashboard: MyDashboard; today: string }) {
  const { t } = usePrefs();
  const blockedIds = new Set(dashboard.blocked.items.map((x) => x.id));
  // Blocked work first (it waits on someone else), then what is past due.
  const items: { task: Task; kind: 'overdue' | 'blocked' }[] = [
    ...dashboard.blocked.items.map((task) => ({ task, kind: 'blocked' as const })),
    ...dashboard.overdue.items.filter((x) => !blockedIds.has(x.id)).map((task) => ({ task, kind: 'overdue' as const })),
  ].slice(0, ATTENTION_SIZE);
  const total = dashboard.blocked.total + dashboard.overdue.items.filter((x) => !blockedIds.has(x.id)).length;

  const note = (task: Task, kind: 'overdue' | 'blocked') => {
    if (kind === 'overdue') {
      const d = daysOverdue(task.due_date, today);
      return d === 1 ? t('This task has passed its due date · 1 day overdue') : t('This task has passed its due date · {n} days overdue', { n: d });
    }
    const days = task.blocked_at ? daysOverdue(task.blocked_at.slice(0, 10), today) : 0;
    return days > 0 ? t(days === 1 ? 'This task has been blocked for {n} day.' : 'This task has been blocked for {n} days.', { n: days }) : t('This task is blocked.');
  };

  return (
    <section className="dv-mw-panel" aria-label={t('Needs Attention')}>
      <div className="head">
        <h2>{t('Needs Attention')}</h2>
        <span className="count">{t(total === 1 ? '{n} task' : '{n} tasks', { n: total })}</span>
      </div>
      {items.length === 0 ? (
        <p className="muted">{t('Nothing is blocked or overdue. Nice work.')}</p>
      ) : (
        <ul>
          {items.map(({ task, kind }) => (
            <li className="alert" key={task.id}>
              <div className="top">
                <div>
                  <h3>{task.title}</h3>
                  <p className="muted">{task.key} · {task.project_name}</p>
                </div>
                <span className="badge red">{kind === 'blocked' ? t('Blocked') : t('Overdue')}</span>
                <Link className="open" to={paths.task(task.id)} aria-label={t('Open {title}', { title: task.title })}><Open /></Link>
              </div>
              <p className="muted note">{note(task, kind)}</p>
              <div className="foot">
                <strong>{task.due_date ? t('Due {date}', { date: fmtDate(task.due_date) }) : t('No due date')}</strong>
                <strong className="prio">{t('{p} priority', { p: t(PRIORITY_LABEL[task.priority]) })}</strong>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
