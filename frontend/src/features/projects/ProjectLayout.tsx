import { useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useOutletContext, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { EXPORT_FORMATS, exportFilter, exportTasks, type ExportFormat } from '@/features/tasks/jiraApi';
import { JiraImportDialog } from '@/features/tasks/JiraImportDialog';
import { useUrlFilter } from '@/features/tasks/useUrlFilter';
import { ApiError, describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { useProject, useProjects } from './projectsApi';
import { PmIcon } from './pmIcons';
import type { Project } from './types';
import '@/features/changeRequests/changeRequests.css';
import '@/features/reports/reports.css';
import '@/features/tasks/tasks.css';
import './projects.css';
import './pmSettings.css';

export const useProjectContext = () => useOutletContext<Project>();

/** Import / Export for the Backlog and Board tabs, shown next to Edit project. Export follows the tab's active filters. */
function BacklogActions({ project }: { project: Project }) {
  const { t: tr } = usePrefs();
  const toast = useToast();
  const { applied } = useUrlFilter();
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportMenu, setExportMenu] = useState(false);

  const runExport = (format: ExportFormat) => {
    setExportMenu(false);
    setExporting(true);
    exportTasks({ project_id: project.id, filter: exportFilter(applied), format })
      .catch((e) => toast.error(describeApiError(e, tr('Could not export tasks.'))))
      .finally(() => setExporting(false));
  };

  return (
    <>
      <button type="button" className="btn secondary" onClick={() => setImporting(true)}>
        {tr('Import')}
      </button>
      <div className="export-menu">
        <button
          type="button"
          className="btn secondary"
          aria-haspopup="menu"
          aria-expanded={exportMenu}
          disabled={exporting}
          onClick={() => setExportMenu((o) => !o)}
          onKeyDown={(e) => e.key === 'Escape' && setExportMenu(false)}
        >
          {tr(exporting ? 'Exporting…' : 'Export')} ▾
        </button>
        {exportMenu && (
          <ul className="export-list" role="menu">
            {EXPORT_FORMATS.map((f) => (
              <li key={f} role="none">
                <button type="button" role="menuitem" onClick={() => runExport(f)}>
                  {f.toUpperCase()}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {importing && <JiraImportDialog projects={[project]} defaultProjectId={project.id} onClose={() => setImporting(false)} />}
    </>
  );
}

/** Read-only archive shown in place of the Overview once a project is completed or cancelled. */
function ClosedProject({ project }: { project: Project }) {
  const { t } = usePrefs();
  return (
    <div className="closed">
      <div className="closed-head">
        <h3>{project.name} · {t(project.status === 'cancelled' ? 'Cancelled' : 'Closed')}</h3>
        <p>{t('The final project record is retained for the project team and authorized client users.')}</p>
      </div>
      <div className="closed-arch">
        <h3>{t('Project archive')}</h3>
        <p>{t('Read-only project history')}</p>
        <ul>
          <li>{t('Requirements and acceptance records')}</li>
          <li>{t('Baseline and approved changes')}</li>
          <li>{t('Milestones and completed work')}</li>
          <li>{t('Final report, decisions and product link')}</li>
        </ul>
      </div>
      <div className="closed-acts">
        <Link className="btn secondary" to={paths.projectReports(project.id)}>{t('Open final report')}</Link>
        <Link className="btn" to={paths.projects}>{t('Back to Projects')}</Link>
      </div>
    </div>
  );
}

/** Project name with a chevron that opens a list of the user's projects (Figma project header). */
function ProjectSwitcher({ project }: { project: Project }) {
  const { t } = usePrefs();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const { data } = useProjects();
  const tail = pathname.split('/').slice(3).join('/');
  const others = (data?.items ?? []).filter((p) => p.id !== project.id);
  return (
    <div className="proj-switch">
      <h1 className="page-title">{project.name}</h1>
      {others.length > 0 && (
        <>
          <button type="button" className="proj-switch-btn" aria-label={t('Switch project')} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            <PmIcon name="chevron" />
          </button>
          {open && (
            <ul className="proj-switch-menu">
              {others.map((p) => (
                <li key={p.id}>
                  <Link to={`${paths.project(p.id)}${tail ? `/${tail}` : ''}`} onClick={() => setOpen(false)}>{p.name}</Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

/** Shell for /projects/:projectId/* with the project header and tab navigation. */
export function ProjectLayout() {
  const { projectId = '' } = useParams();
  const { pathname } = useLocation();
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

  const closed = project.status === 'completed' || project.status === 'cancelled';
  const onBacklog = pathname === paths.projectList(projectId) || pathname === paths.projectBoard(projectId);
  const tabs = [
    { label: 'Overview', to: paths.project(projectId), end: true },
    { label: 'Backlog', to: paths.projectList(projectId) },
    { label: 'Board', to: paths.projectBoard(projectId) },
    ...(user?.role === 'pm'
      ? [
          { label: 'Requirements', to: paths.projectRequirements(projectId) },
          { label: 'Change Requests', to: paths.projectChangeRequests(projectId) },
          { label: 'Milestones', to: paths.projectMilestones(projectId) },
          { label: 'Reports', to: paths.projectReports(projectId) },
          { label: 'Settings', to: paths.projectSettings(projectId) },
        ]
      : []),
  ];

  return (
    <div className="project-page">
      <div className="project-head">
        <div className="page-header">
          <div>
            <div className="proj-eyebrow">{project.type === 'internal' ? t('Internal project') : t('External project')}</div>
            <ProjectSwitcher project={project} />
          </div>
          {user?.role === 'pm' && onBacklog && (
            <div className="page-actions">
              <BacklogActions project={project} />
            </div>
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
      {closed && pathname === paths.project(projectId) ? <ClosedProject project={project} /> : <Outlet context={project} />}
    </div>
  );
}
