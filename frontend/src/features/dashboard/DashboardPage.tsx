import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { parseApiError, useProjects } from '@/features/projects/projectsApi';
import { PmIcon } from '@/features/projects/pmIcons';
import type { Project } from '@/features/projects/types';
import { useDashboard, type DashboardProject, type PmDashboard } from './dashboardApi';
import { STATUS_LABEL, daysOverdue, formatDate, healthOf, todayIso } from '@/features/projects/projectUi';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import '@/features/projects/pmProjects.css';
import './dashboard.css';

const PROJECT_CARDS = 4;
const HEALTH_TONE = { 'On Track': 'good', 'At Risk': 'warn', 'Off Track': 'bad' } as const;

/** Figma "Dashboard" (PM): delivery priorities, four counts, project cards, attention items and next actions. */
export function DashboardPage() {
  const { t } = usePrefs();
  const dashboard = useDashboard();
  const projects = useProjects();

  const newProject = (
    <Link className="btn" to={paths.projectNew}>
      {t('Create New Project')}
    </Link>
  );

  return (
    <section className="page-body dashboard">
      <div className="page-header">
        <h1 className="page-title">{t('Your delivery priorities')}</h1>
        {newProject}
      </div>

      {dashboard.isPending ? (
        <LoadingState title={t('Loading your dashboard')} text={t('Fetching project metrics and items that need attention.')} />
      ) : dashboard.isError ? (
        <ErrorState title={t('We couldn’t load your dashboard')} text={parseApiError(dashboard.error).message} onRetry={() => void dashboard.refetch()} />
      ) : dashboard.data.projects.length === 0 ? (
        <EmptyState title={t('No projects yet')} text={t('Create a project to start tracking work, delivery, and attention items for your team.')} action={newProject} />
      ) : (
        <DashboardBody data={dashboard.data} details={projects.data?.items ?? []} />
      )}
    </section>
  );
}

function DashboardBody({ data, details }: { data: PmDashboard; details: Project[] }) {
  const { t } = usePrefs();
  const today = todayIso();
  const byId = new Map(details.map((p) => [p.id, p]));
  const external = details.filter((p) => p.type === 'external').length;
  const internal = details.length - external;
  const active = data.projects.filter((p) => p.status === 'active');
  const planning = data.projects.filter((p) => p.status === 'planned');
  const shown = data.projects.slice(0, PROJECT_CARDS);
  const firstBlocked = data.blocked.items[0];

  const metrics = [
    { label: t('Total projects'), value: data.projects_total, note: details.length ? t('{e} external · {i} internal', { e: external, i: internal }) : t('Across all projects'), icon: 'folder' as const, tone: 'navy' },
    {
      label: t('Active projects'),
      value: data.active_projects,
      note: data.active_projects === 0 && planning.length ? t('{name} is in planning', { name: planning[0].name }) : t('{n} in total', { n: data.projects_total }),
      icon: 'layers' as const,
      tone: 'blue',
    },
    { label: t('Blocked tasks'), value: data.summary.blocked, note: firstBlocked ? t('{name} needs attention', { name: firstBlocked.title }) : t('Nothing is blocked'), icon: 'ban' as const, tone: 'orange' },
    { label: t('Overdue tasks'), value: data.summary.overdue, note: t('Open tasks past due · {date}', { date: formatDate(today) }), icon: 'clock' as const, tone: 'red' },
  ];

  // Next actions: the delivery date that falls first, then the most urgent task.
  const nextProject = [...active, ...planning]
    .filter((p) => p.target_end_date && p.target_end_date >= today)
    .sort((a, b) => a.target_end_date!.localeCompare(b.target_end_date!))[0];
  const urgent = data.overdue.items[0] ?? firstBlocked;

  return (
    <>
      <section className="metrics" aria-label={t('Metrics overview')}>
        {metrics.map((m) => (
          <article className="metric" key={m.label}>
            <h3>{m.label}</h3>
            <span className={`metric-ico ${m.tone}`}><PmIcon name={m.icon} /></span>
            <strong>{m.value}</strong>
            <span>{m.note}</span>
          </article>
        ))}
      </section>

      <div className="dash-sec">
        <h2>{t('Projects at a glance')}</h2>
        <Link to={paths.projects}>{t('View all projects')}</Link>
      </div>
      <section className="glance">
        {shown.map((p) => (
          <GlanceCard key={p.id} p={p} detail={byId.get(p.id)} />
        ))}
      </section>

      <div className="dash-lower">
        <AttentionAreas data={data} today={today} />
        <section className="card next" aria-label={t('Your next actions')}>
          <h3>{t('Your next actions')}</h3>
          <ul>
            {nextProject && (
              <li>
                <b>{nextProject.name} · {formatDate(nextProject.target_end_date)}</b>
                <span>{t('Delivery date approaching. Review project status.')}</span>
              </li>
            )}
            {urgent && (
              <li>
                <b>{urgent.title}</b>
                <span>{[urgent.project_name, urgent.status.name, urgent.due_date && t('Due {date}', { date: formatDate(urgent.due_date) })].filter(Boolean).join(' · ')}</span>
              </li>
            )}
            {!nextProject && !urgent && <li><span>{t('Nothing needs your action right now.')}</span></li>}
          </ul>
          {urgent && <Link to={paths.task(urgent.id)}>{t('Open my task')}</Link>}
        </section>
      </div>
    </>
  );
}

function GlanceCard({ p, detail }: { p: DashboardProject; detail?: Project }) {
  const { t } = usePrefs();
  const eligible = p.tasks.total;
  const health = healthOf({ status: p.status, task_summary: p.tasks } as Project);
  const external = detail?.type === 'external';
  return (
    <article className="card glance-card">
      <div className="glance-head">
        <span className="glance-ico"><PmIcon name={external ? 'briefcase' : 'layers'} /></span>
        <div>
          <h3><Link to={paths.project(p.id)}>{p.name}</Link></h3>
          <p>{detail?.client_organisation?.name ?? (external ? t('Client project') : t('Internal initiative'))}</p>
        </div>
      </div>
      <div className="tags">
        <span className={`tag ${external ? 'blue' : ''}`}>{t(external ? 'External' : 'Internal')}</span>
        <span className={`tag ${p.status === 'active' ? 'green' : p.status === 'planned' ? 'amber' : ''}`}>{t(p.status === 'active' ? 'Active' : STATUS_LABEL[p.status])}</span>
        <span className={`tag ${eligible ? HEALTH_TONE[health] : ''}`}>{t(eligible ? health : 'Unassessed')}</span>
      </div>
      <div className="glance-row"><span>{t('Task completion')}</span><b>{eligible ? `${Math.round(p.tasks.completion_percent)}%` : '—'}</b></div>
      <div className="glance-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={eligible ? Math.round(p.tasks.completion_percent) : undefined} aria-label={t('{name} completion', { name: p.name })}>
        <i style={{ width: `${eligible ? p.tasks.completion_percent : 0}%` }} />
      </div>
      <p className="glance-note">{eligible ? t('{done} of {total} tasks complete', { done: p.tasks.completed, total: eligible }) : t('No eligible tasks planned yet')}</p>
      <p className="glance-note">{p.target_end_date ? t('Due {date}', { date: formatDate(p.target_end_date) }) : t('Dates to be planned')}</p>
    </article>
  );
}

const overdueText = (due: string | null, today: string, t: (s: string, v?: Record<string, number>) => string) => {
  const d = daysOverdue(due, today);
  return d === 1 ? t('1 day overdue') : t('{n} days overdue', { n: d });
};

function AttentionAreas({ data, today }: { data: PmDashboard; today: string }) {
  const { t } = usePrefs();
  const overdueIds = new Set(data.overdue.items.map((x) => x.id));
  const items = [
    ...data.blocked.items.filter((x) => !overdueIds.has(x.id)).map((task) => ({ task, kind: 'blocked' as const })),
    ...data.overdue.items.map((task) => ({ task, kind: 'overdue' as const })),
  ].slice(0, 4);

  return (
    <section className="card attn" aria-label={t('Needs attention')}>
      <h3>{t('Needs attention')}</h3>
      {items.length === 0 ? (
        <p className="muted attn-note">{t('Nothing is blocked or overdue. Nice work.')}</p>
      ) : (
        <ul className="attn-list">
          {items.map(({ task, kind }) => (
            <li key={task.id}>
              <span className={`attn-ico ${kind}`}><PmIcon name={kind === 'blocked' ? 'warning' : 'clock'} /></span>
              <div>
                <Link to={paths.task(task.id)} className="attn-title">{task.title}</Link>
                <span className="attn-meta">
                  {[
                    t(kind === 'blocked' ? 'Blocked' : 'Overdue'),
                    task.assignee?.name,
                    task.due_date && (kind === 'overdue' ? overdueText(task.due_date, today, t) : t('Due {date}', { date: formatDate(task.due_date) })),
                  ].filter(Boolean).join(' · ')}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
      <Link to={paths.tasks}>{t('Review task list')}</Link>
    </section>
  );
}
