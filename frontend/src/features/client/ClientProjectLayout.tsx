import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useOutletContext, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useClientPortal } from './clientPortalApi';
import type { ClientProject } from './types';
import { EmptyCard, PortalPending } from './ui';

export interface ProjectContext {
  project: ClientProject;
  today: string;
}

export const useProjectContext = () => useOutletContext<ProjectContext>();

const chevron = (
  <svg width="12" height="8" viewBox="0 0 12 8" fill="none" aria-hidden="true">
    <path d="M1 1l5 5 5-5" stroke="#0D1240" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/** Project name with a menu to jump to another shared project. */
function ProjectSwitcher({ current, projects }: { current: ClientProject; projects: ClientProject[] }) {
  const { t } = usePrefs();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);

  return (
    <div className="cp-ptitle" ref={ref}>
      <button type="button" aria-haspopup="true" aria-expanded={open} aria-label={t('Switch project')} onClick={() => setOpen((v) => !v)}>
        {current.name} {chevron}
      </button>
      {open && (
        <nav className="cp-switch" aria-label={t('Projects')}>
          {projects.map((p) => (
            <Link key={p.id} to={paths.clientProject(p.id)} aria-current={p.id === current.id} onClick={() => setOpen(false)}>
              {p.name}
            </Link>
          ))}
        </nav>
      )}
    </div>
  );
}

/** Breadcrumb, project title and the Overview / Milestones / Reports / Change Requests / Contacts tabs. */
export function ClientProjectLayout() {
  const { projectId } = useParams();
  const { t } = usePrefs();
  const query = useClientPortal();
  const { data } = query;
  if (!data) return <PortalPending query={query} />;

  const project = data.projects.find((p) => p.id === projectId);
  if (!project) {
    return (
      <EmptyCard
        title="Project not found"
        text="This project does not exist or has not been shared with you."
        action={<Link to={paths.clientProjects}>{t('Projects')}</Link>}
      />
    );
  }

  const tabs: [string, string, boolean?][] = [
    [paths.clientProject(project.id), 'Overview', true],
    [paths.clientMilestones(project.id), 'Milestones'],
    [paths.clientReports(project.id), 'Reports'],
    [paths.clientChangeRequests(project.id), 'Change Requests'],
    [paths.clientContacts(project.id), 'Contacts'],
  ];

  return (
    <>
      <div className="cp-crumb">
        <Link to={paths.clientProjects}>{t('Projects')}</Link> / {project.name}
      </div>
      <ProjectSwitcher current={project} projects={data.projects} />
      <nav className="cp-tabs" aria-label={t('Project sections')}>
        {tabs.map(([to, label, end]) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => (isActive ? 'cp-on' : undefined)}>
            {t(label)}
          </NavLink>
        ))}
      </nav>
      <Outlet context={{ project, today: data.today } satisfies ProjectContext} />
    </>
  );
}
