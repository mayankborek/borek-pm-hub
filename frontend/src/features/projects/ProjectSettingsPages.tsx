import { Link, Navigate, NavLink } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { initialsOf } from '@/features/projects/MemberPicker';
import { useProjectMembers } from '@/features/tasks/tasksApi';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { useProjectContext } from './ProjectLayout';
import { STATUS_LABEL, formatDate } from './projectUi';
import { useSyncMembers } from './projectsApi';
import type { Project } from './types';
import './pmSettings.css';

/** Sub-navigation shared by both Settings pages (Figma "Settings"). */
function SettingsTabs({ project }: { project: Project }) {
  const { t } = usePrefs();
  return (
    <nav className="set-tabs" aria-label={t('Settings')}>
      <NavLink end to={paths.projectSettings(project.id)} className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('Project details')}</NavLink>
      <NavLink to={paths.projectSettingsPeople(project.id)} className={({ isActive }) => (isActive ? 'active' : undefined)}>{t('People & access')}</NavLink>
    </nav>
  );
}

/** "24–31 Oct 2026" when both dates share a month, otherwise the two full dates. */
function dateRange(start: string | null, end: string | null, t: (s: string) => string) {
  if (!start && !end) return t('Dates to be planned');
  if (start && end) {
    const [sy, sm, sd] = start.split('-');
    const [ey, em] = end.split('-');
    if (sy === ey && sm === em) return `${Number(sd)}–${formatDate(end)}`;
    return `${formatDate(start)} – ${formatDate(end)}`;
  }
  return formatDate(start ?? end);
}

/** Settings → Project details: the essentials, ownership and delivery dates. */
export function ProjectSettingsPage() {
  const project = useProjectContext();
  const { user } = useAuth();
  const { t } = usePrefs();
  if (user?.role !== 'pm') return <Navigate to={paths.project(project.id)} replace />;
  const initials = project.name.split(' ').filter(Boolean).map((w) => w.charAt(0)).join('').slice(0, 2).toUpperCase();

  return (
    <div className="set">
      <SettingsTabs project={project} />
      <div className="set-head">
        <div>
          <h2>{t('Project details')}</h2>
          <p>{t('The essentials, ownership and delivery dates for this project.')}</p>
        </div>
        <Link className="btn" to={paths.projectEdit(project.id)}>{t('Edit details')}</Link>
      </div>
      <div className="set-grid">
        <section className="card set-card">
          <div className="set-id">
            <span className="set-mark">{initials}</span>
            <div>
              <h3>{project.name}</h3>
              <p>{t(project.type === 'internal' ? 'Internal project' : 'External project')}</p>
            </div>
          </div>
          <div className="set-facts">
            <div><span>{t('Project status')}</span><b>{t(STATUS_LABEL[project.status])}</b></div>
            <div><span>{t('Project dates')}</span><b>{dateRange(project.start_date, project.target_end_date, t)}</b></div>
          </div>
          <div className="set-desc">
            <span>{t('Description')}</span>
            <p>{project.description || t('No description yet.')}</p>
          </div>
        </section>
        <aside className="card set-card set-own">
          <h3>{t('Ownership')}</h3>
          <span className="set-label">{t('Project Manager')}</span>
          <div className="set-person"><span className="set-avatar">{initialsOf(user.name)}</span>{user.name}</div>
          <hr />
          <span className="set-label">{t('Client organisation')}</span>
          <b>{project.client_organisation?.name ?? t('Not assigned')}</b>
          {!project.client_organisation && project.type === 'external' && <p>{t('Add a client organisation in Edit details.')}</p>}
        </aside>
      </div>
    </div>
  );
}

/** Settings → People & access: the project manager plus everyone assigned to the project. */
export function ProjectPeoplePage() {
  const project = useProjectContext();
  const { user } = useAuth();
  const { t } = usePrefs();
  const toast = useToast();
  const members = useProjectMembers(project.id);
  const sync = useSyncMembers(project.id);
  if (user?.role !== 'pm') return <Navigate to={paths.project(project.id)} replace />;

  const people = (members.data ?? []).filter((m) => m.user_id !== user.id);
  const total = people.length + 1;
  const remove = (userId: string) =>
    sync.mutate({ add: [], remove: [userId] }, { onError: (e) => toast.error(describeApiError(e, t('Could not remove this person.'))) });

  return (
    <div className="set">
      <SettingsTabs project={project} />
      <div className="set-head">
        <div>
          <h2>{t('People & access')}</h2>
          <p>{t('Manage the people involved in this project and what they can access.')}</p>
        </div>
        <Link className="btn" to={paths.projectEdit(project.id)}>{t('Add developer')}</Link>
      </div>
      {members.isPending ? (
        <LoadingState title={t('Loading people')} text={t('Fetching the project team.')} />
      ) : members.isError ? (
        <ErrorState title={t('We couldn’t load the team')} text={t('Check your connection and try again.')} onRetry={() => void members.refetch()} />
      ) : (
        <section className="card set-people" aria-label={t('Project people')}>
          <header>
            <h3>{t('Project people')} <span className="set-count">{t(total === 1 ? '{n} person' : '{n} people', { n: total })}</span></h3>
            <span>{t('{n} active members', { n: total })}</span>
          </header>
          <table>
            <thead>
              <tr>
                <th>{t('Person')}</th>
                <th>{t('Project role')}</th>
                <th>{t('Access')}</th>
                <th>{t('Status')}</th>
                <th>{t('Actions')}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><span className="set-person"><span className="set-avatar">{initialsOf(user.name)}</span><span><b>{user.name} ({t('you')})</b><small>{t('Internal')}</small></span></span></td>
                <td>{t('Project Manager')}</td>
                <td className="muted">{t('Manage project')}</td>
                <td><span className="set-status">{t('Active')}</span></td>
                <td className="muted">—</td>
              </tr>
              {people.map((m) => (
                <tr key={m.user_id}>
                  <td><span className="set-person"><span className="set-avatar">{initialsOf(m.name)}</span><span><b>{m.name}</b><small>{t('Internal')}</small></span></span></td>
                  <td>{t('Developer')}</td>
                  <td className="muted">{t('Assigned project work')}</td>
                  <td><span className="set-status">{t('Active')}</span></td>
                  <td>
                    <button type="button" className="set-remove" disabled={sync.isPending} onClick={() => remove(m.user_id)}>{t('Remove')}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <footer>{t(total === 1 ? '{n} person in this project' : '{n} people in this project', { n: total })}</footer>
        </section>
      )}
    </div>
  );
}
