import { useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useProjectMembers, type AssignableUser } from '@/features/tasks/tasksApi';
import { useOrganisations } from '@/features/admin/organisationsApi';
import { MemberPicker } from './MemberPicker';
import { parseApiError, useCreateProject, useProject, useSyncMembers, useUpdateProject, type FieldErrors } from './projectsApi';
import { STATUS_LABEL } from './projectUi';
import { PROJECT_STATUSES, type Project, type ProjectInput, type ProjectStatus } from './types';
import './projects.css';

/** The Figma form names the first status "Planning"; other screens keep "Planned". */
const FORM_STATUS_LABEL: Record<ProjectStatus, string> = { ...STATUS_LABEL, planned: 'Planning' };

interface FormState {
  code: string;
  name: string;
  description: string;
  status: ProjectStatus;
  start_date: string;
  target_end_date: string;
  type: 'internal' | 'external';
  /** An organisation id, or NEW_CLIENT to create one together with the project. */
  client: string;
  new_client_name: string;
}

const NEW_CLIENT = '__new__';

const EMPTY: FormState = { code: '', name: '', description: '', status: 'planned', start_date: '', target_end_date: '', type: 'internal', client: '', new_client_name: '' };

const fromProject = (p: Project): FormState => ({
  code: p.code,
  name: p.name,
  description: p.description ?? '',
  status: p.status,
  start_date: p.start_date ?? '',
  target_end_date: p.target_end_date ?? '',
  type: p.type ?? 'internal',
  client: p.client_organisation?.id ?? '',
  new_client_name: '',
});

/** Mirrors the backend rules so most mistakes are caught before the request. The server stays the authority. */
function validate(f: FormState, isEdit: boolean, t: (s: string) => string): FieldErrors {
  const e: FieldErrors = {};
  if (!isEdit) {
    if (!f.code.trim()) e.code = t('Project code is required.');
    else if (f.code.trim().length > 20) e.code = t('Use 20 characters or fewer.');
  }
  if (!f.name.trim()) e.name = t('Project name is required.');
  else if (f.name.trim().length > 200) e.name = t('Use 200 characters or fewer.');
  if (f.start_date && f.target_end_date && f.target_end_date < f.start_date) {
    e.target_end_date = t('Target end date cannot be before the start date.');
  }
  if (f.type === 'external') {
    if (!f.client) e.client = t('Choose a client for an external project.');
    else if (f.client === NEW_CLIENT && !f.new_client_name.trim()) e.new_client_name = t('Client name is required.');
  }
  return e;
}

const toInput = (f: FormState, isEdit: boolean): ProjectInput => {
  const base: ProjectInput = {
    code: f.code.trim(),
    name: f.name.trim(),
    description: f.description.trim() || null,
    status: f.status,
    start_date: f.start_date || null,
    target_end_date: f.target_end_date || null,
    type: f.type,
  };
  if (f.type === 'internal') return isEdit ? { ...base, client_organisation_id: null } : base;
  if (f.client === NEW_CLIENT) return { ...base, new_client: { name: f.new_client_name.trim() } };
  return { ...base, client_organisation_id: f.client };
};

export function ProjectCreatePage() {
  return <ProjectForm />;
}

export function ProjectEditPage() {
  const { projectId = '' } = useParams();
  const { data, isPending, isError, refetch } = useProject(projectId);
  const members = useProjectMembers(projectId);
  if (isPending || members.isPending) return <LoadingState title="Loading project" />;
  if (isError || members.isError) return <ErrorState title="We couldn’t load this project" onRetry={() => void refetch()} />;
  const current: AssignableUser[] = members.data.map((m) => ({ id: m.user_id, name: m.name, email: m.email, role: 'developer' }));
  return <ProjectForm project={data} currentMembers={current} />;
}

function ProjectForm({ project, currentMembers = [] }: { project?: Project; currentMembers?: AssignableUser[] }) {
  const { t } = usePrefs();
  const isEdit = !!project;
  const navigate = useNavigate();
  const create = useCreateProject();
  const update = useUpdateProject(project?.id ?? '');
  const [form, setForm] = useState<FormState>(project ? fromProject(project) : EMPTY);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState('');
  const [members, setMembers] = useState<AssignableUser[]>(currentMembers);
  const syncMembers = useSyncMembers(project?.id ?? '');
  const clients = useOrganisations();
  const saving = create.isPending || update.isPending || syncMembers.isPending;
  const back = project ? paths.project(project.id) : paths.projects;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => ({ ...e, [key]: '' }));
  };

  const onSubmit = async (ev: FormEvent) => {
    ev.preventDefault();
    setFormError('');
    const found = validate(form, isEdit, t);
    setErrors(found);
    if (Object.keys(found).length) return;

    try {
      const input = toInput(form, isEdit);
      if (project) {
        const { code: _code, ...rest } = input;
        await update.mutateAsync({ input: rest, version: project.version });
        const before = new Set(currentMembers.map((m) => m.id));
        const after = new Set(members.map((m) => m.id));
        const add = [...after].filter((id) => !before.has(id));
        const remove = [...before].filter((id) => !after.has(id));
        if (add.length || remove.length) await syncMembers.mutateAsync({ add, remove });
        navigate(paths.project(project.id));
      } else {
        const created = await create.mutateAsync({ ...input, members: members.map((m) => ({ user_id: m.id })) });
        navigate(paths.project(created.id));
      }
    } catch (err) {
      const parsed = parseApiError(err);
      setErrors(parsed.fields);
      setFormError(parsed.message);
    }
  };

  const field = (id: keyof FormState, label: string, input: ReactNode, hint?: string) => (
    <div className="field">
      <label htmlFor={id}>{t(label)}</label>
      {input}
      {hint && !errors[id] && <span className="hint">{t(hint)}</span>}
      {errors[id] && (
        <span className="field-error" id={`${id}-error`}>
          {t(errors[id] ?? '')}
        </span>
      )}
    </div>
  );

  const aria = (id: keyof FormState) => ({ 'aria-invalid': !!errors[id], 'aria-describedby': errors[id] ? `${id}-error` : undefined });

  const title = isEdit ? 'Edit Project' : 'Create Project';

  return (
    <section className="pform">
      <div className="pform-head">
        <p className="pform-crumb">{t('Projects  /  All Projects')}</p>
        <h2>{t(title)}</h2>
      </div>

      <form className="pform-body" onSubmit={(e) => void onSubmit(e)} noValidate>
        {formError && (
          <div className="form-alert" role="alert">
            {t(formError)}
          </div>
        )}

        <div className="pform-section">
          <span className="pform-icon" aria-hidden="true">
            <i /><i /><i /><i />
          </span>
          <div>
            <h3>{t('Project Details')}</h3>
            <p>{t('Give your team a clear starting point.')}</p>
          </div>
        </div>

        <div className="pform-row two">
          {field('name', 'Project Name *', <input id="name" className="input" placeholder={t('e.g. Website redesign')} value={form.name} maxLength={200} onChange={(e) => set('name', e.target.value)} {...aria('name')} />)}
          {field(
            'code',
            'Unique Code',
            <input
              id="code"
              className="input"
              placeholder={t('e.g. BFL-WEB')}
              value={form.code}
              maxLength={20}
              disabled={isEdit}
              onChange={(e) => set('code', e.target.value.toUpperCase())}
              {...aria('code')}
            />,
            isEdit ? 'The code cannot be changed after creation.' : undefined,
          )}
        </div>

        {field(
          'description',
          'Description',
          <textarea id="description" className="input" placeholder={t('Describe the outcome, scope, or goal for this project.')} value={form.description} onChange={(e) => set('description', e.target.value)} />,
        )}

        <div className="pform-row sched">
          {field(
            'status',
            'Status',
            <select id="status" className="input" value={form.status} onChange={(e) => set('status', e.target.value as ProjectStatus)}>
              {PROJECT_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(FORM_STATUS_LABEL[s])}
                </option>
              ))}
            </select>,
          )}
          {field('start_date', 'Start Date', <input id="start_date" type="date" className="input" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} />)}
          {field(
            'target_end_date',
            'Target End Date',
            <input id="target_end_date" type="date" className="input" value={form.target_end_date} min={form.start_date || undefined} onChange={(e) => set('target_end_date', e.target.value)} {...aria('target_end_date')} />,
          )}
        </div>

        <div className="pform-row two">
          {field(
            'type',
            'Project Type',
            <select id="type" className="input" value={form.type} onChange={(e) => set('type', e.target.value as FormState['type'])}>
              <option value="internal">{t('Internal')}</option>
              <option value="external">{t('External (for a client)')}</option>
            </select>,
          )}
          {form.type === 'external' &&
            field(
              'client',
              'Client *',
              <select id="client" className="input" value={form.client} onChange={(e) => set('client', e.target.value)} {...aria('client')}>
                <option value="">{t('Select a client')}</option>
                {(clients.data?.items ?? []).map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
                {!isEdit && <option value={NEW_CLIENT}>{t('+ New client…')}</option>}
              </select>,
            )}
        </div>
        {form.type === 'external' &&
          form.client === NEW_CLIENT &&
          field('new_client_name', 'New Client Name *', <input id="new_client_name" className="input" maxLength={200} value={form.new_client_name} onChange={(e) => set('new_client_name', e.target.value)} {...aria('new_client_name')} />)}

        <div className="field">
          <label htmlFor="members">{t('Add Members')}</label>
          <MemberPicker selected={members} onChange={setMembers} />
        </div>

        <div className="pform-actions">
          <Link className="pform-btn" to={back}>
            {t('Cancel')}
          </Link>
          <button type="submit" className="pform-btn primary" disabled={saving}>
            {t(saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Project')}
          </button>
        </div>
      </form>
    </section>
  );
}
