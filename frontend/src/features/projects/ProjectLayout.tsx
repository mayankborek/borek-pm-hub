import { Link, NavLink, Outlet, useOutletContext, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { ApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useProject } from './projectsApi';
import type { Project } from './types';
import './projects.css';

export const useProjectContext = () => useOutletContext<Project>();

/** Shell for /projects/:projectId/* with the project header and tab navigation. */
export function ProjectLayout() {
  const { projectId = '' } = useParams();
  const { user } = useAuth();
  const { t } = usePrefs();
  const { data: project, isPending, error, refetch } = useProject(projectId);

  if (isPending) return <LoadingState title="Loading project" text="Fetching project details." />;
  if (error || !project) {
    // The backend answers 404 for projects the user cannot see, so both cases read the same.
    const missing = error instanceof ApiError && (error.status === 404 || error.status === 403);
    return missing ? (
      <ErrorState
        title="Project not found"
        text="It may have been removed, or you may not have access to it."
        onRetry={undefined}
      />
    ) : (
      <ErrorState title="We couldn’t load this project" text="Check your connection and try again." onRetry={() => void refetch()} />
    );
  }

  const tabs = [
    { label: 'Overview', to: paths.project(projectId), end: true },
    { label: 'Backlog', to: paths.projectList(projectId) },
    { label: 'Board', to: paths.projectBoard(projectId) },
  ];

  return (
    <>
      <nav className="crumbs" aria-label={t('Breadcrumb')}>
        <Link to={paths.projects}>{t('Projects')}</Link>
        <span aria-hidden="true"> / </span>
        <span>{project.name}</span>
      </nav>
      <div className="project-head">
        <div className="page-header">
          <div>
            <h1 className="page-title">{project.name}</h1>
            <p className="project-sub">{t('Project overview, task status, and delivery summary.')}</p>
          </div>
          {user?.role === 'pm' && (
            <Link className="btn secondary" to={paths.projectEdit(project.id)}>
              {t('Edit project')}
            </Link>
          )}
        </div>
        <nav className="tabs" aria-label={t('Project')}>
          {tabs.map((tab) => (
            <NavLink key={tab.to} to={tab.to} end={tab.end} className={({ isActive }) => (isActive ? 'tab active' : 'tab')}>
              {t(tab.label)}
            </NavLink>
          ))}
        </nav>
      </div>
      <Outlet context={project} />
    </>
  );
}
