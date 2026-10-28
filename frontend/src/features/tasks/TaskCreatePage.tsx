import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { ApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useProjects } from '@/features/projects/projectsApi';
import { useCreateTask, useProjectMembers, useProjectStatuses } from './tasksApi';
import '@/features/projects/projects.css';

/** Add Task (Figma "Workflow · Create task · Ready"): POST /projects/{id}/tasks, then opens the new task. */
export function TaskCreatePage() {
  const { t } = usePrefs();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [title, setTitle] = useState('');
  const [projectId, setProjectId] = useState(params.get('project_id') ?? '');
  const [assigneeId, setAssigneeId] = useState('');
  const [statusId, setStatusId] = useState('');
  const [titleError, setTitleError] = useState('');
  const projects = useProjects();
  const members = useProjectMembers(projectId);
  const statuses = useProjectStatuses(projectId);
  const create = useCreateTask(projectId);

  const projectList = projects.data?.items ?? [];
  // New tasks default to the project's Backlog status.
  const defaultStatus = statuses.data?.find((s) => s.category === 'backlog') ?? statuses.data?.find((s) => s.category === 'todo') ?? statuses.data?.[0];
  const status = statuses.data?.some((s) => s.id === statusId) ? statusId : (defaultStatus?.id ?? '');

  const onProject = (id: string) => {
    setProjectId(id);
    setAssigneeId('');
    setStatusId('');
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return setTitleError(t('Task title is required.'));
    if (!projectId) return;
    create.mutate(
      { title: title.trim(), status_id: status || undefined, assignee_id: assigneeId || null },
      { onSuccess: (task) => navigate(paths.task(task.id)) },
    );
  };

  return (
    <section className="page-body narrow">
      <form className="card form" onSubmit={onSubmit} noValidate>
        <h1 className="page-title">{t('Create task')}</h1>
        {create.isError && (
          <div className="form-alert" role="alert">
            {create.error instanceof ApiError ? create.error.message : t('Could not create the task. Try again.')}
          </div>
        )}

        <div className="field">
          <label htmlFor="task-title">{t('Task title *')}</label>
          <input
            id="task-title"
            className="input"
            autoFocus
            maxLength={300}
            placeholder={t('Draft release checklist')}
            value={title}
            aria-invalid={!!titleError}
            aria-describedby={titleError ? 'task-title-error' : undefined}
            onChange={(e) => {
              setTitle(e.target.value);
              setTitleError('');
            }}
          />
          {titleError && (
            <span className="field-error" id="task-title-error">
              {titleError}
            </span>
          )}
        </div>

        <div className="field">
          <label htmlFor="task-project">{t('Project')}</label>
          <select id="task-project" className="input" value={projectId} onChange={(e) => onProject(e.target.value)}>
            <option value="" disabled>
              {t('Select a project')}
            </option>
            {projectList.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="task-assignee">{t('Assignee')}</label>
          <select id="task-assignee" className="input" value={assigneeId} disabled={!projectId} onChange={(e) => setAssigneeId(e.target.value)}>
            <option value="">{t('Unassigned')}</option>
            {(members.data ?? []).map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="task-status">{t('Status')}</label>
          <select id="task-status" className="input" value={status} disabled={!projectId} onChange={(e) => setStatusId(e.target.value)}>
            {!status && <option value="">{t('To do')}</option>}
            {(statuses.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {t(s.name)}
              </option>
            ))}
          </select>
        </div>

        <div className="form-actions">
          <Link className="btn secondary" to={paths.tasks}>
            {t('Cancel')}
          </Link>
          <button type="submit" className="btn" disabled={!projectId || create.isPending}>
            {t(create.isPending ? 'Creating…' : 'Create task')}
          </button>
        </div>
      </form>
    </section>
  );
}
