import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { parseApiError } from '@/features/projects/projectsApi';
import { useDashboard, type DashboardProject, type PmDashboard } from './dashboardApi';
import { STATUS_LABEL, daysOverdue, formatDate, todayIso } from '@/features/projects/projectUi';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Pill } from '@/shared/ui/Pill';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import './dashboard.css';

const PROJECT_ROWS = 12;

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? 'Good Morning' : h < 18 ? 'Good Afternoon' : 'Good Evening';
};

/** Same rule as the project list: on hold is off track, blocked or overdue work is at risk. */
const healthOf = (p: DashboardProject) =>
  p.status === 'on_hold' ? 'Off Track' : p.tasks.blocked > 0 || p.tasks.overdue > 0 ? 'At Risk' : 'On Track';

export function DashboardPage() {
  const { user } = useAuth();
  const { t } = usePrefs();
  const dashboard = useDashboard();
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

      {dashboard.isPending ? (
        <LoadingState title={t('Loading your dashboard')} text={t('Fetching project metrics and items that need attention.')} />
      ) : dashboard.isError ? (
        <ErrorState title={t('We couldn’t load your dashboard')} text={parseApiError(dashboard.error).message} onRetry={() => void dashboard.refetch()} />
      ) : dashboard.data.projects.length === 0 ? (
        <EmptyState title={t('No projects yet')} text={t('Create a project to start tracking work, delivery, and attention items for your team.')} action={newProject} />
      ) : (
        <DashboardBody data={dashboard.data} />
      )}
    </section>
  );
}

function DashboardBody({ data }: { data: PmDashboard }) {
  const { t } = usePrefs();
  const total = data.projects_total;
  const metrics = [
    { label: t('Active Projects'), value: data.active_projects, note: t('{n} in total', { n: total }) },
    { label: t('Tasks in Progress'), value: data.summary.in_progress, note: t('Across all projects') },
    { label: t('Blocked Tasks'), value: data.summary.blocked, note: t('Needs PM action') },
    { label: t('Overdue Tasks'), value: data.summary.overdue, note: t('Needs PM action') },
  ];
  const shown = data.projects.slice(0, PROJECT_ROWS);

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

        <AttentionAreas data={data} />
      </div>
    </>
  );
}

const overdueText = (due: string | null, today: string, t: (s: string, v?: Record<string, number>) => string) => {
  const d = daysOverdue(due, today);
  return d === 1 ? t('1 day overdue') : t('{n} days overdue', { n: d });
};

function AttentionAreas({ data }: { data: PmDashboard }) {
  const { t } = usePrefs();
  const today = todayIso();
  const overdueIds = new Set(data.overdue.items.map((x) => x.id));
  const items = [
    ...data.overdue.items.map((task) => ({ task, kind: 'overdue' as const })),
    ...data.blocked.items.filter((x) => !overdueIds.has(x.id)).map((task) => ({ task, kind: 'blocked' as const })),
  ].slice(0, 6);

  return (
    <section className="card attn" aria-label={t('Attention Areas')}>
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
                  {task.project_name}
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
