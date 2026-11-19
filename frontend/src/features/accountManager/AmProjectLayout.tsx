import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useClientPortal } from '@/features/client/clientPortalApi';
import type { ProjectContext } from '@/features/client/ClientProjectLayout';
import type { ClientProject } from '@/features/client/types';
import { EmptyCard, PortalPending } from '@/features/client/ui';
import '@/features/client/clientPortal.css';
import '@/features/admin/admin.css';

/** Project name with a menu to jump to another project. */
function Switcher({ current, projects }: { current: ClientProject; projects: ClientProject[] }) {
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
    <div className="ptitle pswitch" ref={ref}>
      <h1>{current.name}</h1>
      <button type="button" aria-haspopup="true" aria-expanded={open} aria-label={t('Switch project')} onClick={() => setOpen((v) => !v)}>⌄</button>
      {open && (
        <nav aria-label={t('Projects')}>
          {projects.map((p) => (
            <Link key={p.id} to={paths.amProject(p.id)} aria-current={p.id === current.id} onClick={() => setOpen(false)}>{p.name}</Link>
          ))}
        </nav>
      )}
    </div>
  );
}

/** Project header (borek-flow-portal/project.html): breadcrumb, title and the Overview / Milestones / Reports / Stakeholders tabs. */
export function AmProjectLayout() {
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
        action={<Link to={paths.amProjects}>{t('Projects')}</Link>}
      />
    );
  }
  const tabs: [string, string, boolean?][] = [
    [paths.amProject(project.id), 'Overview', true],
    [paths.amMilestones(project.id), 'Milestones'],
    [paths.amReports(project.id), 'Reports'],
    [paths.amStakeholders(project.id), 'Stakeholders'],
  ];

  return (
    <div className="am-page">
      <div className="crumb"><Link to={paths.amProjects}>{t('Projects')}</Link> / {project.name}</div>
      <Switcher current={project} projects={data.projects} />
      <nav className="tabs" aria-label={t('Project sections')}>
        {tabs.map(([to, label, end]) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => (isActive ? 'active' : undefined)}>{t(label)}</NavLink>
        ))}
      </nav>
      <Outlet context={{ project, today: data.today } satisfies ProjectContext} />
    </div>
  );
}
