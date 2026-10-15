import { NavLink, Outlet, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';

/** Shell for /projects/:projectId/* with tab navigation. */
export function ProjectLayout() {
  const { projectId = '' } = useParams();
  const tabs = [
    { label: 'Board', to: paths.projectBoard(projectId) },
    { label: 'List', to: paths.projectList(projectId) },
    { label: 'Members', to: paths.projectMembers(projectId) },
  ];

  return (
    <>
      <div className="project-head">
        <h1 className="page-title">Project {projectId}</h1>
        <nav className="tabs" aria-label="Project">
          {tabs.map((t) => (
            <NavLink key={t.to} to={t.to} className={({ isActive }) => (isActive ? 'tab active' : 'tab')}>
              {t.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <Outlet />
    </>
  );
}
