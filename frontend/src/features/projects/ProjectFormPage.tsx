import { useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import type { AssignableUser } from '@/features/tasks/tasksApi';
import { MemberPicker } from './MemberPicker';
import { parseApiError, useCreateProject, useProject, useUpdateProject, type FieldErrors } from './projectsApi';
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
}

const EMPTY: FormState = { code: '', name: '', description: '', status: 'planned', start_date: '', target_end_date: '' };

const fromProject = (p: Project): FormState => ({
  code: p.code,
  name: p.name,
  description: p.description ?? '',
  status: p.status,
  start_date: p.start_date ?? '',
  target_end_date: p.target_end_date ?? '',
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
  return e;
}

const toInput = (f: FormState): ProjectInput => ({
  code: f.code.trim(),
  name: f.name.trim(),
  description: f.description.trim() || null,
  status: f.status,
  start_date: f.start_date || null,
  target_end_date: f.target_end_date || null,
});

export function ProjectCreatePage() {
  return <ProjectForm />;
}

export function ProjectEditPage() {
  const { projectId = '' } = useParams();
  const { data, isPending, isError, refetch } = useProject(projectId);
  if (isPending) return <LoadingState title="Loading project" />;
  if (isError) return <ErrorState title="We couldn’t load this project" onRetry={() => void refetch()} />;
  return <ProjectForm project={data} />;
}

function ProjectForm({ project }: { project?: Project }) {
  const { t } = usePrefs();
  const isEdit = !!project;
  const navigate = useNavigate();
  const create = useCreateProject();
  const update = useUpdateProject(project?.id ?? '');
  const [form, setForm] = useState<FormState>(project ? fromProject(project) : EMPTY);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState('');
  const [members, setMembers] = useState<AssignableUser[]>([]);
  const saving = create.isPending || update.isPending;
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
      const input = toInput(form);
      if (project) {
        const { code: _code, ...rest } = input;
        await update.mutateAsync({ input: rest, version: project.version });
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

        {!isEdit && (
          <div className="field">
            <label htmlFor="members">{t('Add Members')}</label>
            <MemberPicker selected={members} onChange={setMembers} />
          </div>
        )}

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
