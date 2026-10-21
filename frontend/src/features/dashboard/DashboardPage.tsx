import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { parseApiError, useProjects } from '@/features/projects/projectsApi';
import { useBlockedTasks, useDueSoonTasks, useOverdueTasks } from './dashboardApi';
import { STATUS_LABEL, addDaysIso, daysOverdue, formatDate, healthOf, todayIso } from '@/features/projects/projectUi';
import type { Project, TaskListItem } from '@/features/projects/types';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Pill } from '@/shared/ui/Pill';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import './dashboard.css';

const PROJECT_ROWS = 12;
const sum = (projects: Project[], pick: (p: Project) => number | undefined) =>
  projects.reduce((n, p) => n + (pick(p) ?? 0), 0);

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? 'Good Morning' : h < 18 ? 'Good Afternoon' : 'Good Evening';
};

export function DashboardPage() {
  const { user } = useAuth();
  const { t } = usePrefs();
  const projects = useProjects();
  const firstName = user?.name.split(' ')[0] ?? '';

  const newProject = (
    <Link className="btn" to={paths.projectNew}>
      {t('New Project')}
    </Link>
  );

  return (
    <section className="page-body dashboard">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            {t(greeting())}, {firstName}
          </h1>
          <p className="page-desc">{t('Portfolio health, team delivery, and attention items across active projects.')}</p>
        </div>
        {newProject}
      </div>

      {projects.isPending ? (
        <LoadingState title={t('Loading your dashboard')} text={t('Fetching project metrics and items that need attention.')} />
      ) : projects.isError ? (
        <ErrorState title={t('We couldn’t load your projects')} text={parseApiError(projects.error).message} onRetry={() => void projects.refetch()} />
      ) : projects.data.items.length === 0 ? (
        <EmptyState title={t('No projects yet')} text={t('Create a project to start tracking work, delivery, and attention items for your team.')} action={newProject} />
      ) : (
        <DashboardBody projects={projects.data.items} total={projects.data.total} />
      )}
    </section>
  );
}

function DashboardBody({ projects, total }: { projects: Project[]; total: number }) {
  const { t } = usePrefs();
  const hasSummary = projects.some((p) => p.task_summary);
  const today = todayIso();
  const dueSoon = useDueSoonTasks(today, addDaysIso(7));
  const active = projects.filter((p) => p.status === 'active').length;
  const metrics = [
    { label: t('Active Projects'), value: active, note: t('{n} in total', { n: total }) },
    { label: t('Tasks in Progress'), value: hasSummary ? sum(projects, (p) => p.task_summary?.in_progress) : '—', note: t('Across all projects') },
    { label: t('Due this Week'), value: dueSoon.data ? dueSoon.data.length : '—', note: t('Next 7 days') },
    { label: t('Overdue Tasks'), value: hasSummary ? sum(projects, (p) => p.task_summary?.overdue) : '—', note: t('Needs PM action') },
  ];
  const shown = projects.slice(0, PROJECT_ROWS);

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
        <section className="card" aria-label={t('Projects')}>
          <h3>{t('All Accessible Projects')}</h3>
          <p className="desc">
            {t(total === 1 ? '{n} project available to you' : '{n} projects available to you', { n: total })}
          </p>
          <div className="proj-head" aria-hidden="true">
            <span>{t('Project')}</span>
            <span>{t('Lifecycle')}</span>
            <span>{t('Health')}</span>
          </div>
          <ul className="proj-list">
            {shown.map((p) => {
              const health = healthOf(p);
              return (
                <li key={p.id}>
                  <Link to={paths.project(p.id)}>{p.name} →</Link>
                  <span className={`life ${p.status}`}>{t(STATUS_LABEL[p.status])}</span>
                  <span className={`health ${health.replace(' ', '-').toLowerCase()}`}>{t(health)}</span>
                </li>
              );
            })}
          </ul>
          {total > shown.length && (
            <Link className="more" to={paths.projects}>
              {t('View all {n} projects →', { n: total })}
            </Link>
          )}
        </section>

        <AttentionAreas projects={projects} />
      </div>
    </>
  );
}

const overdueText = (due: string | null, today: string, t: (s: string, v?: Record<string, number>) => string) => {
  const d = daysOverdue(due, today);
  return d === 1 ? t('1 day overdue') : t('{n} days overdue', { n: d });
};

function AttentionAreas({ projects }: { projects: Project[] }) {
  const { t } = usePrefs();
  const today = todayIso();
  const overdue = useOverdueTasks(today);
  const blocked = useBlockedTasks();
  const names = new Map(projects.map((p) => [p.id, p.name]));

  const items: { task: TaskListItem; kind: 'overdue' | 'blocked' }[] = [
    ...(overdue.data ?? []).map((task) => ({ task, kind: 'overdue' as const })),
    ...(blocked.data ?? [])
      .filter((t) => !(overdue.data ?? []).some((o) => o.id === t.id))
      .map((task) => ({ task, kind: 'blocked' as const })),
  ].slice(0, 6);

  const loading = overdue.isPending || blocked.isPending;
  const failed = overdue.isError || blocked.isError;

  return (
    <section className="card" aria-label={t('Attention Areas')}>
      <h3>{t('Attention Areas')}</h3>
      <p className="desc">{t('Blocked or overdue work needing attention')}</p>
      {loading ? (
        <p className="muted attn-note" aria-busy="true">
          {t('Loading…')}
        </p>
      ) : null}
      {!loading && failed && (
        <p className="muted attn-note" role="alert">
          {overdue.isError && blocked.isError
            ? t('Attention items are unavailable right now.')
            : t(overdue.isError ? 'Overdue tasks could not be loaded.' : 'Blocked tasks could not be loaded.')}{' '}
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              void overdue.refetch();
              void blocked.refetch();
            }}
          >
            {t('Retry')}
          </button>
        </p>
      )}
      {!loading && !failed && items.length === 0 ? (
        <p className="muted attn-note">{t('Nothing is blocked or overdue. Nice work.')}</p>
      ) : null}
      {!loading && items.length > 0 && (
        <ul className="attn-list">
          {items.map(({ task, kind }) => (
            <li key={task.id}>
              <Link to={paths.task(task.id)} className={kind === 'overdue' ? 'attn-title warn' : 'attn-title err'}>
                {task.key} · {task.title}
              </Link>
              <div className="attn-meta">
                <span>
                  {task.project_name ?? names.get(task.project_id) ?? 'Project'}
                  {kind === 'overdue' ? ` · ${formatDate(task.due_date)} · ${overdueText(task.due_date, today, t)}` : ` · ${t('blocked')}`}
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
