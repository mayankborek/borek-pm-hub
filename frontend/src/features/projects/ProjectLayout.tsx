import { useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useOutletContext, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { exportFilter, exportTasks } from '@/features/tasks/jiraApi';
import { JiraImportDialog } from '@/features/tasks/JiraImportDialog';
import { useUrlFilter } from '@/features/tasks/useUrlFilter';
import { ApiError, describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { usePendingChangeRequests } from '@/features/changeRequests/changeRequestsStaffApi';
import { useProject } from './projectsApi';
import type { Project } from './types';
import '@/features/changeRequests/changeRequests.css';
import './projects.css';

export const useProjectContext = () => useOutletContext<Project>();

/** Import / Export for the Backlog and Board tabs, shown next to Edit project. Export follows the tab's active filters. */
function BacklogActions({ project }: { project: Project }) {
  const { t: tr } = usePrefs();
  const toast = useToast();
  const { applied } = useUrlFilter();
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);

  const runExport = () => {
    setExporting(true);
    exportTasks({ project_id: project.id, filter: exportFilter(applied) })
      .catch((e) => toast.error(describeApiError(e, tr('Could not export tasks.'))))
      .finally(() => setExporting(false));
  };

  return (
    <>
      <button type="button" className="btn secondary" onClick={() => setImporting(true)}>
        {tr('Import')}
      </button>
      <button type="button" className="btn secondary" disabled={exporting} onClick={runExport}>
        {tr(exporting ? 'Exporting…' : 'Export')}
      </button>
      {importing && <JiraImportDialog projects={[project]} defaultProjectId={project.id} onClose={() => setImporting(false)} />}
    </>
  );
}

/** Shell for /projects/:projectId/* with the project header and tab navigation. */
export function ProjectLayout() {
  const { projectId = '' } = useParams();
  const { pathname } = useLocation();
  const { user } = useAuth();
  const { t } = usePrefs();
  const { data: project, isPending, error, refetch } = useProject(projectId);
  const pendingRequests = usePendingChangeRequests(projectId, user?.role === 'pm').data ?? 0;

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

  const onBacklog = pathname === paths.projectList(projectId) || pathname === paths.projectBoard(projectId);
  const tabs = [
    { label: 'Overview', to: paths.project(projectId), end: true },
    { label: 'Backlog', to: paths.projectList(projectId) },
    { label: 'Board', to: paths.projectBoard(projectId) },
    ...(user?.role === 'pm'
      ? [
          { label: 'Requirements', to: paths.projectRequirements(projectId) },
          { label: 'Change Requests', to: paths.projectChangeRequests(projectId), badge: pendingRequests },
        ]
      : []),
  ];

  return (
    <div className="project-page">
      <div className="project-head">
        <div className="page-header">
          <div>
            <div className="proj-eyebrow">{project.code}</div>
            <h1 className="page-title">{project.name}</h1>
          </div>
          {user?.role === 'pm' && (
            <div className="page-actions">
              {onBacklog && <BacklogActions project={project} />}
              <Link className="btn secondary" to={paths.projectEdit(project.id)}>
                {t('Edit project')}
              </Link>
            </div>
          )}
        </div>
        <nav className="tabs" aria-label={t('Project')}>
          {tabs.map((tab) => (
            <NavLink key={tab.to} to={tab.to} end={tab.end} className={({ isActive }) => (isActive ? 'tab active' : 'tab')}>
              {t(tab.label)}
              {!!tab.badge && <span className="crq-badge" aria-label={t('{n} new', { n: tab.badge })}>{tab.badge}</span>}
            </NavLink>
          ))}
        </nav>
      </div>
      <Outlet context={project} />
    </div>
  );
}
