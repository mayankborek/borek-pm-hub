import { useState, type FormEvent } from 'react';
import { Link, Navigate, NavLink, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { initialsOf } from '@/features/projects/MemberPicker';
import { useProjectMembers } from '@/features/tasks/tasksApi';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { useProjectContext } from './ProjectLayout';
import { STATUS_LABEL } from './projectUi';
import { useOrganisations } from '@/features/admin/organisationsApi';
import { parseApiError, useSyncMembers, useUpdateProject, type FieldErrors } from './projectsApi';
import { PROJECT_STATUSES, type Project, type ProjectInput, type ProjectStatus } from './types';
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

/** Settings → Edit project details (project-settings.html): general information, ownership and delivery schedule. */
export function ProjectSettingsPage() {
  const project = useProjectContext();
  const { user } = useAuth();
  const { t } = usePrefs();
  const navigate = useNavigate();
  const update = useUpdateProject(project.id);
  const clients = useOrganisations();
  const initial = {
    name: project.name,
    type: project.type ?? 'internal',
    status: project.status,
    description: project.description ?? '',
    client: project.client_organisation?.id ?? '',
    start_date: project.start_date ?? '',
    target_end_date: project.target_end_date ?? '',
  };
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState('');
  if (user?.role !== 'pm') return <Navigate to={paths.project(project.id)} replace />;

  const set = <K extends keyof typeof initial>(key: K, value: (typeof initial)[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => ({ ...e, [key]: '' }));
  };

  const onSubmit = (ev: FormEvent) => {
    ev.preventDefault();
    setFormError('');
    const found: FieldErrors = {};
    if (!form.name.trim()) found.name = t('Project name is required.');
    if (!form.start_date) found.start_date = t('Start date is required.');
    if (form.start_date && form.target_end_date && form.target_end_date < form.start_date) found.target_end_date = t('Target end date cannot be before the start date.');
    if (form.type === 'external' && !form.client) found.client = t('Choose a client for an external project.');
    setErrors(found);
    if (Object.keys(found).length) return;
    const input: Omit<ProjectInput, 'code'> = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      status: form.status,
      start_date: form.start_date || null,
      target_end_date: form.target_end_date || null,
      type: form.type,
      category: project.category ?? null,
      priority: project.priority,
      client_organisation_id: form.type === 'external' ? form.client : null,
    };
    update.mutate(
      { input, version: project.version },
      {
        onSuccess: () => navigate(paths.project(project.id)),
        onError: (err) => {
          const parsed = parseApiError(err);
          setErrors(parsed.fields);
          setFormError(parsed.message);
        },
      },
    );
  };

  const err = (id: string) => errors[id] && <span className="ps-err">{errors[id]}</span>;

  return (
    <div className="ps">
      <h2 className="ps-h2">{t('Edit project details')}</h2>
      <p className="ps-lead">{t('Update the project information, ownership and delivery schedule.')}</p>
      {formError && (
        <div className="form-alert" role="alert">
          {t(formError)}
        </div>
      )}
      <form
        onSubmit={onSubmit}
        onReset={() => {
          setForm(initial);
          setErrors({});
          setFormError('');
        }}
        noValidate
      >
        <div className="ps-grid">
          <section className="ps-card">
            <h3>{t('General information')}</h3>
            <p>{t('Keep the project name and description easy to recognise.')}</p>
            <label className="ps-f">
              {t('Project name')}
              <input value={form.name} maxLength={200} onChange={(e) => set('name', e.target.value)} aria-invalid={!!errors.name} />
              {err('name')}
            </label>
            <div className="ps-two">
              <label className="ps-f">
                {t('Project type')}
                <select value={form.type} onChange={(e) => set('type', e.target.value as 'internal' | 'external')}>
                  <option value="external">{t('External project')}</option>
                  <option value="internal">{t('Internal project')}</option>
                </select>
              </label>
              <label className="ps-f">
                {t('Project status')}
                <select value={form.status} onChange={(e) => set('status', e.target.value as ProjectStatus)}>
                  {PROJECT_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {t(STATUS_LABEL[s])}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="ps-f">
              {t('Description')}
              <textarea value={form.description} onChange={(e) => set('description', e.target.value)} />
            </label>
          </section>
          <div>
            <section className="ps-card">
              <h3>{t('Ownership')}</h3>
              <p>{t('Choose who is responsible for this project.')}</p>
              <label className="ps-f">
                {t('Project Manager')}
                <select value={user.id} disabled>
                  <option value={user.id}>{user.name}</option>
                </select>
              </label>
              <label className="ps-f">
                {t('Client organisation')}
                <select value={form.client} disabled={form.type === 'internal'} onChange={(e) => set('client', e.target.value)} aria-invalid={!!errors.client}>
                  <option value="">{t('Select client organisation')}</option>
                  {(clients.data?.items ?? []).map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
                {err('client')}
              </label>
            </section>
            <section className="ps-card ps-sched">
              <h3>{t('Delivery schedule')}</h3>
              <p>{t('Set the planned start and target finish.')}</p>
              <div className="ps-two">
                <label className="ps-f">
                  {t('Start date')}
                  <input type="date" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} aria-invalid={!!errors.start_date} />
                  {err('start_date')}
                </label>
                <label className="ps-f">
                  {t('Target finish')}
                  <input type="date" value={form.target_end_date} min={form.start_date || undefined} onChange={(e) => set('target_end_date', e.target.value)} aria-invalid={!!errors.target_end_date} />
                  {err('target_end_date')}
                </label>
              </div>
            </section>
            <div className="ps-actions">
              <button type="reset" className="ps-btn">
                {t('Cancel')}
              </button>
              <button type="submit" className="ps-btn primary" disabled={update.isPending}>
                {t(update.isPending ? 'Saving…' : 'Save changes')}
              </button>
            </div>
          </div>
        </div>
      </form>
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
