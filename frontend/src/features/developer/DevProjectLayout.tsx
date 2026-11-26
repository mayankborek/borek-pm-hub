import { Link, NavLink, Outlet, useLocation, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ApiError } from '@/shared/api/client';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { usePopover } from '@/features/admin/AdminUi';
import { useProject, useProjects } from '@/features/projects/projectsApi';
import type { Project } from '@/features/projects/types';
import { Chevron } from './devUi';

/** Project name with a chevron that opens the developer's other projects, keeping the current tab. */
function Switcher({ project }: { project: Project }) {
  const { t } = usePrefs();
  const { pathname } = useLocation();
  const pop = usePopover();
  const { data } = useProjects();
  const tail = pathname.split('/').slice(3).join('/');
  const others = (data?.items ?? []).filter((p) => p.id !== project.id);
  return (
    <div className="dv-switch" ref={pop.ref}>
      <h2>{project.name}</h2>
      {others.length > 0 && (
        <>
          <button type="button" aria-label={t('Switch project')} aria-haspopup="true" aria-expanded={pop.open} onClick={() => pop.setOpen((o) => !o)}>
            <Chevron size={16} />
          </button>
          {pop.open && (
            <ul className="dv-pop dv-switch-list">
              {others.map((p) => (
                <li key={p.id}>
                  <Link to={`${paths.project(p.id)}${tail ? `/${tail}` : ''}`} onClick={() => pop.setOpen(false)}>{p.name}</Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

/** Project header (borek-flow-screens): External / Internal eyebrow, project name, then the Overview, Backlog and Board tabs. */
export function DevProjectLayout() {
  const { projectId = '' } = useParams();
  const { t } = usePrefs();
  const { data: project, isPending, error, refetch } = useProject(projectId);

  if (isPending) return <LoadingState title="Loading project" text="Fetching project details." />;
  if (error || !project) {
    const missing = error instanceof ApiError && (error.status === 404 || error.status === 403);
    return missing ? (
      <ErrorState title="Project not found" text="It may have been removed, or you may not have access to it." onRetry={undefined} />
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
    <div className="dv-project">
      <header>
        <small>{project.type === 'internal' ? t('Internal') : t('External')}</small>
        <Switcher project={project} />
        <nav className="dv-tabs" aria-label={t('Project')}>
          {tabs.map((tab) => (
            <NavLink key={tab.to} to={tab.to} end={tab.end} className={({ isActive }) => (isActive ? 'on' : undefined)}>{t(tab.label)}</NavLink>
          ))}
        </nav>
      </header>
      <Outlet context={project} />
    </div>
  );
}
