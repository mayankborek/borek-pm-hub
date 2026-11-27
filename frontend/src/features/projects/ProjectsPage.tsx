import { useState } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useProjects } from './projectsApi';
import type { Project } from './types';
import emptyIllustration from './assets/empty-projects.jpg';
import { PmIcon } from './pmIcons';
import { STATUS_LABEL, completionOf, formatDate, healthOf } from './projectUi';
import { PROJECT_STATUSES, type ProjectStatus } from './types';
import './projects.css';
import './pmProjects.css';
import '@/features/tasks/tasks.css';

const HEALTH_TONE = { 'On Track': 'good', 'At Risk': 'warn', 'Off Track': 'bad' } as const;

/** "Projects at a glance" cards on the left, the portfolio summary on the right. Both roles see the projects the backend lets them see. */
function ProjectGrid({ projects, total }: { projects: Project[]; total: number }) {
  const { t } = usePrefs();
  const isPm = useAuth().user?.role === 'pm';
  const [status, setStatus] = useState<ProjectStatus | ''>('');
  const shown = status ? projects.filter((p) => p.status === status) : projects;
  const count = (s: ProjectStatus) => projects.filter((p) => p.status === s).length;
  const external = projects.filter((p) => p.type === 'external').length;
  return (
    <>
      <div className="pj-bar">
        <h2>{t(isPm ? 'All projects' : 'My projects')} · {total}</h2>
        <select className="pj-filter" aria-label={t('Filter by status')} value={status} onChange={(e) => setStatus(e.target.value as ProjectStatus | '')}>
          <option value="">{t('All projects')}</option>
          {PROJECT_STATUSES.map((s) => (
            <option key={s} value={s}>{t(STATUS_LABEL[s])}</option>
          ))}
        </select>
      </div>
      <div className="pj-layout">
        <div className="pj-cards">
          {shown.length === 0 && <p className="muted">{t('No projects with this status.')}</p>}
          {shown.map((p) => {
            const eligible = p.task_summary?.total ?? 0;
            const pct = Math.round(completionOf(p));
            const health = healthOf(p);
            const ext = p.type === 'external';
            return (
              <article className="card pj-card" key={p.id}>
                <div className="glance-head">
                  <span className="glance-ico"><PmIcon name={ext ? 'briefcase' : 'layers'} /></span>
                  <div>
                    <h3>{p.name}</h3>
                    <p>{ext ? [p.client_organisation?.name, t('Client project')].filter(Boolean).join(' · ') : `Borek · ${t('Internal initiative')}`}</p>
                  </div>
                </div>
                <div className="tags">
                  <span className={`tag ${ext ? 'blue' : ''}`}>{t(ext ? 'External' : 'Internal')}</span>
                  <span className={`tag ${p.status === 'active' ? 'blue' : ''}`}>{t(STATUS_LABEL[p.status])}</span>
                  <span className={`tag ${eligible ? HEALTH_TONE[health] : ''}`}>{t(eligible ? health : 'Unassessed')}</span>
                </div>
                <div className="glance-row"><span>{t('Task completion')}</span><b>{eligible ? `${pct}%` : '—'}</b></div>
                <div className="glance-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={eligible ? pct : undefined} aria-label={t('{name} completion', { name: p.name })}>
                  <i style={{ width: `${eligible ? pct : 0}%` }} />
                </div>
                <p className="glance-note">{eligible ? t('{done} of {total} tasks complete', { done: p.task_summary?.completed ?? 0, total: eligible }) : t('No eligible tasks planned yet')}</p>
                {!!p.task_summary?.overdue && <p className="glance-note"><b>{t(p.task_summary.overdue === 1 ? '{n} task overdue' : '{n} tasks overdue', { n: p.task_summary.overdue })}</b></p>}
                <p className="glance-note">{p.target_end_date ? t('Due {date}', { date: formatDate(p.target_end_date) }) : t('Dates to be planned')}</p>
                <Link className="pj-open" to={paths.project(p.id)}>{t('View project')} →</Link>
              </article>
            );
          })}
        </div>
        <aside className="card pj-portfolio" aria-label={t('Your Portfolio')}>
          <h3>{t('Your Portfolio')}</h3>
          <strong>{t(total === 1 ? '{n} project' : '{n} projects', { n: total })}</strong>
          <h4>{t('By status')}</h4>
          <div className="pj-stats">
            {PROJECT_STATUSES.filter((s) => count(s) > 0).map((s) => (
              <div key={s} className={s === 'active' ? 'on' : ''}><span>{t(STATUS_LABEL[s])}</span><b>{count(s)}</b></div>
            ))}
          </div>
          <h4>{t('By project type')}</h4>
          <dl>
            <div><dt>{t('External project')}</dt><dd>{external}</dd></div>
            <div><dt>{t('Internal project')}</dt><dd>{projects.length - external}</dd></div>
          </dl>
        </aside>
      </div>
    </>
  );
}

export function ProjectsPage() {
  const { user } = useAuth();
  const { t } = usePrefs();
  const isPm = user?.role === 'pm';
  const [search, setSearch] = useState('');
  const { data, isPending, isError, refetch, isFetching } = useProjects(search);

  const newButton = isPm && (
    <Link className="btn" to={paths.projectNew}>
      {t('Create New Project')}
    </Link>
  );

  const page = (
    <section className={`page-body task-list-page${isPm ? '' : ' dev-projects'}`}>
      <div className="page-header">
        <div>
          <h1 className="page-title">{t(isPm ? 'Projects' : 'My projects')}</h1>
          <p className="page-desc">{t(isPm ? 'Plan delivery, monitor progress and keep your team aligned.' : 'Projects you can access. Open a project to see its overview and tasks.')}</p>
        </div>
        {newButton}
      </div>

      <div className="toolbar task-filters" hidden={isPm || (data?.total === 0 && !search.trim())}>
        <input
          type="search"
          className="input"
          placeholder={t('Search by name or code')}
          aria-label={t('Search projects')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {isFetching && !isPending && <span className="muted">{t('Updating…')}</span>}
      </div>

      {isPending ? (
        <LoadingState title="Loading projects" text="Fetching the projects you can access." />
      ) : isError ? (
        <ErrorState title="We couldn’t load your projects" text="Check your connection and try again." onRetry={() => void refetch()} />
      ) : data.items.length === 0 ? (
        search.trim() ? (
          <EmptyState title="No matching projects" text={t('Nothing matches “{q}”. Try a different name or code.', { q: search.trim() })} />
        ) : !isPm ? (
          <section className="state center empty-art">
            <img src={emptyIllustration} alt="" width={254} height={254} />
            <h3>{t('No projects you can access yet')}</h3>
            <p>{t('When you’re added to a project, it will appear here. Create a project or ask a project manager to grant access.')}</p>
          </section>
        ) : (
          <EmptyState
            title="No projects yet"
            text={isPm ? 'Create a project to start tracking work and delivery for your team.' : 'You have not been added to any project yet.'}
            action={newButton || undefined}
          />
        )
      ) : (
        <ProjectGrid projects={data.items} total={data.total} />
      )}
    </section>
  );
  // The PM card styles are scoped to `.shell.pm`; developers sit in their own shell, so they get that scope here.
  return isPm ? page : <div className="shell pm" style={{ display: 'contents' }}>{page}</div>;
}
