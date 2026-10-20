import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { useBlockedTasks, useDueSoonTasks, useOverdueTasks, useProjects } from '@/features/projects/projectsApi';
import { STATUS_LABEL, addDaysIso, formatDate, healthOf, todayIso } from '@/features/projects/projectUi';
import type { Project, TaskListItem } from '@/features/projects/types';
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
  const projects = useProjects();
  const firstName = user?.name.split(' ')[0] ?? '';

  const newProject = (
    <Link className="btn" to={paths.projectNew}>
      New Project
    </Link>
  );

  return (
    <section className="page-body dashboard">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            {greeting()}, {firstName}
          </h1>
          <p className="page-desc">Portfolio health, team delivery, and attention items across active projects.</p>
        </div>
        {newProject}
      </div>

      {projects.isPending ? (
        <LoadingState title="Loading your dashboard" text="Fetching project metrics and items that need attention." />
      ) : projects.isError ? (
        <ErrorState title="We couldn’t load your projects" text="Check your connection and try again." onRetry={() => void projects.refetch()} />
      ) : projects.data.items.length === 0 ? (
        <EmptyState title="No projects yet" text="Create a project to start tracking work, delivery, and attention items for your team." action={newProject} />
      ) : (
        <DashboardBody projects={projects.data.items} total={projects.data.total} />
      )}
    </section>
  );
}

function DashboardBody({ projects, total }: { projects: Project[]; total: number }) {
  const hasSummary = projects.some((p) => p.task_summary);
  const today = todayIso();
  const dueSoon = useDueSoonTasks(today, addDaysIso(7));
  const active = projects.filter((p) => p.status === 'active').length;
  const metrics = [
    { label: 'Active Projects', value: active, note: `${total} in total` },
    { label: 'Tasks in Progress', value: hasSummary ? sum(projects, (p) => p.task_summary?.in_progress) : '—', note: 'Across all projects' },
    { label: 'Due this Week', value: dueSoon.data ? dueSoon.data.length : '—', note: 'Next 7 days' },
    { label: 'Overdue Tasks', value: hasSummary ? sum(projects, (p) => p.task_summary?.overdue) : '—', note: 'Needs PM action' },
  ];
  const shown = projects.slice(0, PROJECT_ROWS);

  return (
    <>
      <section className="metrics" aria-label="Metrics overview">
        {metrics.map((m) => (
          <article className="metric" key={m.label}>
            <h3>{m.label}</h3>
            <strong>{m.value}</strong>
            <span>{m.note}</span>
          </article>
        ))}
      </section>

      <div className="split">
        <section className="card" aria-label="Projects">
          <h3>All Accessible Projects</h3>
          <p className="desc">
            {total} {total === 1 ? 'project' : 'projects'} available to you
          </p>
          <div className="proj-head" aria-hidden="true">
            <span>Project</span>
            <span>Lifecycle</span>
            <span>Health</span>
          </div>
          <ul className="proj-list">
            {shown.map((p) => {
              const health = healthOf(p);
              return (
                <li key={p.id}>
                  <Link to={paths.project(p.id)}>{p.name} →</Link>
                  <span className={`life ${p.status}`}>{STATUS_LABEL[p.status]}</span>
                  <span className={`health ${health.replace(' ', '-').toLowerCase()}`}>{health}</span>
                </li>
              );
            })}
          </ul>
          {total > shown.length && (
            <Link className="more" to={paths.projects}>
              View all {total} projects →
            </Link>
          )}
        </section>

        <AttentionAreas projects={projects} />
      </div>
    </>
  );
}

function AttentionAreas({ projects }: { projects: Project[] }) {
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
  const failed = overdue.isError && blocked.isError;

  return (
    <section className="card" aria-label="Attention areas">
      <h3>Attention Areas</h3>
      <p className="desc">Blocked or overdue work needing attention</p>
      {loading ? (
        <p className="muted attn-note" aria-busy="true">
          Loading…
        </p>
      ) : failed ? (
        <p className="muted attn-note" role="alert">
          Attention items are unavailable right now.{' '}
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              void overdue.refetch();
              void blocked.refetch();
            }}
          >
            Retry
          </button>
        </p>
      ) : items.length === 0 ? (
        <p className="muted attn-note">Nothing is blocked or overdue. Nice work.</p>
      ) : (
        <ul className="attn-list">
          {items.map(({ task, kind }) => (
            <li key={task.id}>
              <Link to={paths.task(task.id)} className={kind === 'overdue' ? 'attn-title warn' : 'attn-title err'}>
                {task.key} · {task.title}
              </Link>
              <div className="attn-meta">
                <span>
                  {task.project_name ?? names.get(task.project_id) ?? 'Project'}
                  {kind === 'overdue' ? ` · due ${formatDate(task.due_date)}` : ' · blocked'}
                </span>
                <Pill tone={kind === 'overdue' ? 'overdue' : 'blocked'}>{kind === 'overdue' ? 'Overdue' : 'Blocked'}</Pill>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
