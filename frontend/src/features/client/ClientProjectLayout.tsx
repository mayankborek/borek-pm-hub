import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useOutletContext, useParams } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthContext';
import { paths } from '@/app/routes';
import { usePortalPaths } from './portalPaths';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useClientPortal } from './clientPortalApi';
import type { ClientProject } from './types';
import { Icon } from './icons';
import { EmptyCard, PortalPending } from './ui';
import './clientScreens.css';

export interface ProjectContext {
  project: ClientProject;
  today: string;
}

export const useProjectContext = () => useOutletContext<ProjectContext>();

/** Project name with a menu to jump to another shared project. */
function ProjectSwitcher({ current, projects }: { current: ClientProject; projects: ClientProject[] }) {
  const pp = usePortalPaths();
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
    <h1 className="cx-h-proj" ref={ref}>
      <button type="button" aria-haspopup="true" aria-expanded={open} aria-label={t('Switch project')} onClick={() => setOpen((v) => !v)}>
        {current.name} <Icon name="chevron" className="cx-ico" strokeWidth={2} />
      </button>
      {open && (
        <nav className="cx-switch" aria-label={t('Projects')}>
          {projects.map((p) => (
            <Link key={p.id} to={pp.project(p.id)} aria-current={p.id === current.id} onClick={() => setOpen(false)}>
              {p.name}
            </Link>
          ))}
        </nav>
      )}
    </h1>
  );
}

/** Project title and the Overview / Milestones / Reports / Change Requests / Contacts tabs. */
export function ClientProjectLayout() {
  const pp = usePortalPaths();
  const role = useAuth().user?.role;
  const isAm = role === 'account_manager';
  const isManager = role === 'manager';
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
        action={<Link to={pp.projects}>{t('Projects')}</Link>}
      />
    );
  }

  const tabs: [string, string, boolean?][] = isAm
    ? [
        [pp.project(project.id), 'Overview', true],
        [pp.milestones(project.id), 'Milestones'],
        [pp.reports(project.id), 'Reports'],
        [pp.people(project.id), 'Stakeholders'],
      ]
    : [
        [pp.project(project.id), 'Overview', true],
        [pp.milestones(project.id), 'Milestones'],
        [pp.reports(project.id), 'Reports'],
        ...(isManager ? [] : ([[paths.clientRequirements(project.id), 'Requirements']] as [string, string][])),
        [pp.changeRequests(project.id), 'Change Requests'],
        [pp.people(project.id), isManager ? 'Stakeholders' : 'Contacts'],
      ];

  return (
    <>
      <ProjectSwitcher current={project} projects={data.projects} />
      <nav className="cx-tabs" aria-label={t('Project sections')}>
        {tabs.map(([to, label, end]) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => (isActive ? 'cx-on' : undefined)}>
            {t(label)}
          </NavLink>
        ))}
      </nav>
      <Outlet context={{ project, today: data.today } satisfies ProjectContext} />
    </>
  );
}
