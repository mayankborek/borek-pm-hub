import { useState } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { Pill, ProgressBar } from '@/shared/ui/Pill';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useProjects } from './projectsApi';
import { STATUS_LABEL, STATUS_TONE, completionOf, formatDate } from './projectUi';
import './projects.css';

export function ProjectsPage() {
  const { user } = useAuth();
  const isPm = user?.role === 'pm';
  const [search, setSearch] = useState('');
  const { data, isPending, isError, refetch, isFetching } = useProjects(search);

  const newButton = isPm && (
    <Link className="btn" to={paths.projectNew}>
      New Project
    </Link>
  );

  return (
    <section className="page-body">
      <div className="page-header">
        <div>
          <h1 className="page-title">Projects</h1>
          <p className="page-desc">Projects you can access. Open a project to see its overview and tasks.</p>
        </div>
        {newButton}
      </div>

      <div className="toolbar">
        <input
          type="search"
          className="input"
          placeholder="Search by name or code"
          aria-label="Search projects"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {isFetching && !isPending && <span className="muted">Updating…</span>}
      </div>

      {isPending ? (
        <LoadingState title="Loading projects" text="Fetching the projects you can access." />
      ) : isError ? (
        <ErrorState title="We couldn’t load your projects" text="Check your connection and try again." onRetry={() => void refetch()} />
      ) : data.items.length === 0 ? (
        search.trim() ? (
          <EmptyState title="No matching projects" text={`Nothing matches “${search.trim()}”. Try a different name or code.`} />
        ) : (
          <EmptyState
            title="No projects yet"
            text={isPm ? 'Create a project to start tracking work and delivery for your team.' : 'You have not been added to any project yet.'}
            action={newButton || undefined}
          />
        )
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Project</th>
                <th>Status</th>
                <th>Progress</th>
                <th className="num">Tasks</th>
                <th className="num">Overdue</th>
                <th>Target end</th>
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
                    <ProgressBar percent={completionOf(p)} label={`${p.name} completion`} />
                  </td>
                  <td className="num">{p.task_summary?.total ?? '—'}</td>
                  <td className={p.task_summary?.overdue ? 'num warn' : 'num'}>{p.task_summary?.overdue ?? '—'}</td>
                  <td>{formatDate(p.target_end_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="table-foot muted small">
            {data.total} {data.total === 1 ? 'project' : 'projects'}
          </div>
        </div>
      )}
    </section>
  );
}
