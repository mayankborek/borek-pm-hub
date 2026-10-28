import { useState } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Pill, ProgressBar } from '@/shared/ui/Pill';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useProjects } from './projectsApi';
import type { Project } from './types';
import emptyIllustration from './assets/empty-projects.jpg';
import { STATUS_LABEL, STATUS_TONE, completionOf, formatDate } from './projectUi';
import './projects.css';
import '@/features/tasks/tasks.css';

/** Developer "My Projects" grid, styled like the PM Task List (Figma "01 PM Task List — Primary"). */
function DevProjectGrid({ projects, total }: { projects: Project[]; total: number }) {
  const { t } = usePrefs();
  return (
    <>
      <section className="task-group table" role="table" aria-label={t('My projects')}>
        <div className="task-row task-table-head proj-row" role="row">
          <div role="columnheader">{t('Project / Code')}</div>
          <div role="columnheader">{t('Status')}</div>
          <div role="columnheader">{t('Progress')}</div>
          <div role="columnheader">{t('Tasks')}</div>
          <div role="columnheader">{t('Overdue')}</div>
          <div role="columnheader">{t('Target end')}</div>
        </div>
        {projects.map((p) => (
          <div className="task-row proj-row" role="row" key={p.id}>
            <div className="task-title" role="cell">
              <span className="task-title-stack">
                <Link to={paths.project(p.id)}>{p.name}</Link>
                <span className="proj-code">{p.code}</span>
              </span>
            </div>
            <div role="cell">
              <Pill tone={STATUS_TONE[p.status]}>{STATUS_LABEL[p.status]}</Pill>
            </div>
            <div role="cell">
              <ProgressBar percent={completionOf(p)} label={t('{name} completion', { name: p.name })} />
            </div>
            <div className="cell-muted" role="cell">
              {p.task_summary?.total ?? '—'}
            </div>
            <div className={p.task_summary?.overdue ? 'warn' : 'cell-muted'} role="cell">
              {p.task_summary?.overdue ?? '—'}
            </div>
            <div className="cell-muted" role="cell">
              {formatDate(p.target_end_date)}
            </div>
          </div>
        ))}
      </section>
      <p className="task-foot">
        {t(total === 1 ? 'Showing {n} of {total} project' : 'Showing {n} of {total} projects', { n: projects.length, total })}
      </p>
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
      {t('New Project')}
    </Link>
  );

  return (
    <section className="page-body">
      <div className="page-header">
        <div>
          {!isPm && <p className="page-crumb">{t('Workspace / Projects assigned to me')}</p>}
          <h1 className="page-title">{t(isPm ? 'Projects' : 'My projects')}</h1>
          {isPm && <p className="page-desc">{t('Projects you can access. Open a project to see its overview and tasks.')}</p>}
        </div>
        {newButton}
      </div>

      <div className={isPm ? 'toolbar' : 'toolbar task-filters'} hidden={!isPm && data?.total === 0 && !search.trim()}>
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
      ) : !isPm ? (
        <DevProjectGrid projects={data.items} total={data.total} />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Project')}</th>
                <th>{t('Status')}</th>
                <th>{t('Progress')}</th>
                <th className="num">{t('Tasks')}</th>
                <th className="num">{t('Overdue')}</th>
                <th>{t('Target end')}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link className="row-link" to={paths.project(p.id)}>
                      {p.name}
                    </Link>
                    <div className="muted small">{p.code}</div>
                  </td>
                  <td>
                    <Pill tone={STATUS_TONE[p.status]}>{STATUS_LABEL[p.status]}</Pill>
                  </td>
                  <td>
                    <ProgressBar percent={completionOf(p)} label={t('{name} completion', { name: p.name })} />
                  </td>
                  <td className="num">{p.task_summary?.total ?? '—'}</td>
                  <td className={p.task_summary?.overdue ? 'num warn' : 'num'}>{p.task_summary?.overdue ?? '—'}</td>
                  <td>{formatDate(p.target_end_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="table-foot muted small">
            {t(data.total === 1 ? '{n} project' : '{n} projects', { n: data.total })}
          </div>
        </div>
      )}
    </section>
  );
}
