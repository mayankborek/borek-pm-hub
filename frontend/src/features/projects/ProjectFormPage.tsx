import { useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useProjectMembers, type AssignableUser } from '@/features/tasks/tasksApi';
import { PrioritySelect } from '@/features/tasks/PrioritySelect';
import { useOrganisations } from '@/features/admin/organisationsApi';
import { MemberPicker } from './MemberPicker';
import { parseApiError, useCreateProject, useProject, useSyncMembers, useUpdateProject, usePicklist, type FieldErrors } from './projectsApi';
import { STATUS_LABEL } from './projectUi';
import { PROJECT_STATUSES, type Project, type ProjectInput, type ProjectStatus } from './types';
import './projects.css';
import './pmForm.css';

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
  contact_name: string;
  contact_email: string;
  category: string;
  priority: NonNullable<Project['priority']>;
}

const NEW_CLIENT = '__new__';

const EMPTY: FormState = { code: '', name: '', description: '', status: 'planned', start_date: '', target_end_date: '', type: 'internal', client: '', new_client_name: '', contact_name: '', contact_email: '', category: '', priority: 'medium' };

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
  contact_name: '',
  contact_email: '',
  category: p.category ?? '',
  priority: p.priority ?? 'medium',
});

/** Mirrors the backend rules so most mistakes are caught before the request. The server stays the authority. */
function validate(f: FormState, isEdit: boolean, t: (s: string) => string): FieldErrors {
  const e: FieldErrors = {};
  if (!isEdit) {
    if (!f.code.trim()) e.code = t('Project code is required.');
    else if (f.code.trim().length > 20) e.code = t('Use 20 characters or fewer.');
  }
  if (!f.category.trim()) e.category = t('Choose a category.');
  if (!f.start_date) e.start_date = t('Start date is required.');
  if (!f.name.trim()) e.name = t('Project name is required.');
  else if (f.name.trim().length > 200) e.name = t('Use 200 characters or fewer.');
  if (f.start_date && f.target_end_date && f.target_end_date < f.start_date) {
    e.target_end_date = t('Target end date cannot be before the start date.');
  }
  if (f.type === 'external') {
    if (!f.client) e.client = t('Choose a client for an external project.');
    else if (f.client === NEW_CLIENT) {
      if (!f.new_client_name.trim()) e.new_client_name = t('Client name is required.');
      if (f.contact_name.trim() && !f.contact_email.trim()) e.contact_email = t('Add the contact email.');
      if (f.contact_email.trim() && !f.contact_name.trim()) e.contact_name = t('Add the contact name.');
    }
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
    category: f.category.trim() || null,
    priority: f.priority,
  };
  if (f.type === 'internal') return isEdit ? { ...base, client_organisation_id: null } : base;
  if (f.client === NEW_CLIENT) return { ...base, new_client: { name: f.new_client_name.trim(), ...(f.contact_email.trim() && { contact: { name: f.contact_name.trim(), email: f.contact_email.trim() } }) } };
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
  const categoryList = usePicklist('project_category');
  const isNew = form.client === NEW_CLIENT;
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

  const categories = [...new Set([...(categoryList.data ?? []), ...(form.category ? [form.category] : [])])];

  return (
    <section className="pform pform-new">
      <div className="intro">
        <p>{t('Projects')} &nbsp;/&nbsp; {project ? project.name : t('All Projects')}</p>
        <h1>{t(isEdit ? 'Edit Project' : 'Create Project')}</h1>
        <p className="lede">{t(isEdit ? 'Update the details and team of this project.' : 'Set up a shared space for your team’s work.')}</p>
      </div>
      <form className="pf" onSubmit={(e) => void onSubmit(e)} noValidate>
        <div className="ptitle">
          <span className="tile">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path fill="#0F8B7A" d="M0 0h6v6H0z" /><path fill="#1F5FD6" d="M10 0h6v6h-6zM0 10h6v6H0zM10 10h6v6h-6z" /></svg>
          </span>
          <div>
            <h2>{t('Project Details')}</h2>
            <p>{t('Review the marked fields before creating the project.')}</p>
          </div>
        </div>
        {formError && <div className="form-alert" role="alert">{t(formError)}</div>}

        <div className="grid top-row">
          {field('name', 'Project Name *', <input id="name" className="input" autoComplete="off" value={form.name} maxLength={200} onChange={(e) => set('name', e.target.value)} {...aria('name')} />)}
          {field(
            'code',
            'Unique Code *',
            <input id="code" className="input" autoComplete="off" placeholder={t('e.g. BFL-WEB')} value={form.code} maxLength={20} disabled={isEdit} onChange={(e) => set('code', e.target.value.toUpperCase())} {...aria('code')} />,
            isEdit ? 'The code cannot be changed after creation.' : undefined,
          )}
        </div>
        <div className="desc">
          {field('description', 'Description', <textarea id="description" className="input" placeholder={t('Describe the outcome, scope, or goal for this project.')} value={form.description} onChange={(e) => set('description', e.target.value)} />)}
        </div>
        <div className="grid three">
          {field(
            'status',
            'Status',
            <select id="status" className="input" value={form.status} onChange={(e) => set('status', e.target.value as ProjectStatus)}>
              {PROJECT_STATUSES.map((s) => (
                <option key={s} value={s}>{t(STATUS_LABEL[s])}</option>
              ))}
            </select>,
          )}
          {field('start_date', 'Start Date *', <input id="start_date" type="date" className="input" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} {...aria('start_date')} />)}
          {field('target_end_date', 'Target End Date', <input id="target_end_date" type="date" className="input" value={form.target_end_date} min={form.start_date || undefined} onChange={(e) => set('target_end_date', e.target.value)} {...aria('target_end_date')} />)}
        </div>
        <div className="grid three">
          {field(
            'type',
            'Project Type',
            <select id="type" className="input" value={form.type} onChange={(e) => set('type', e.target.value as FormState['type'])}>
              <option value="internal">{t('Internal')} · {t('Company projects')}</option>
              <option value="external">{t('External')} · {t('Client projects')}</option>
            </select>,
          )}
          {field(
            'category',
            'Category *',
            <select id="category" className="input" value={form.category} onChange={(e) => set('category', e.target.value)} {...aria('category')}>
              <option value="">{t('Select a category')}</option>
              {categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>,
          )}
          <div className="field">
            <label>{t('Priority')}</label>
            <PrioritySelect value={form.priority} onChange={(p) => set('priority', p)} />
          </div>
        </div>

        {form.type === 'external' && (
          <div className="pf-client">
            <div className="pf-tabs" role="tablist">
              <button type="button" role="tab" aria-selected={!isNew} className={!isNew ? 'on' : ''} onClick={() => set('client', form.client === NEW_CLIENT ? '' : form.client)}>{t('Existing client')}</button>
              {!isEdit && (
                <button type="button" role="tab" aria-selected={isNew} className={isNew ? 'on' : ''} onClick={() => set('client', NEW_CLIENT)}>{t('New client')}</button>
              )}
            </div>
            {isNew ? (
              <div className="grid three">
                {field('new_client_name', 'Client organisation *', <input id="new_client_name" className="input" maxLength={200} value={form.new_client_name} onChange={(e) => set('new_client_name', e.target.value)} {...aria('new_client_name')} />)}
                {field('contact_name', 'Contact name', <input id="contact_name" className="input" maxLength={200} value={form.contact_name} onChange={(e) => set('contact_name', e.target.value)} {...aria('contact_name')} />)}
                {field('contact_email', 'Contact email', <input id="contact_email" type="email" className="input" maxLength={320} value={form.contact_email} onChange={(e) => set('contact_email', e.target.value)} {...aria('contact_email')} />)}
              </div>
            ) : (
              <div className="grid">
                {field(
                  'client',
                  'Client organisation *',
                  <select id="client" className="input" value={form.client} onChange={(e) => set('client', e.target.value)} {...aria('client')}>
                    <option value="">{t('Select client organisation')}</option>
                    {(clients.data?.items ?? []).map((o) => (
                      <option key={o.id} value={o.id}>{o.name}</option>
                    ))}
                  </select>,
                )}
              </div>
            )}
          </div>
        )}

        <div className="field members">
          <label htmlFor="members">{t('Add Members')}</label>
          <MemberPicker selected={members} onChange={setMembers} />
        </div>

        <div className="end">
          <Link className="pform-btn" to={back}>{t('Cancel')}</Link>
          <button type="submit" className="pform-btn primary" disabled={saving}>
            {t(saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Project')}
          </button>
        </div>
      </form>
    </section>
  );
}
