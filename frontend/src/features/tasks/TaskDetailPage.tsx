import { useRef, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { ApiError, describeApiError } from '@/shared/api/client';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import {
  downloadAttachment,
  useActivity,
  useAddComment,
  useAttachmentActions,
  useComments,
  useAttachments,
  useProjectStatuses,
  useTask,
  useUpdateTask,
  ESTIMATE_UNITS,
  type EstimateUnit,
  type Task,
  type TaskPatch,
} from './tasksApi';
import { formatDate } from '@/features/projects/projectUi';
import { RelatedTaskDrawer, relationLabels, type Relationship } from './RelatedTaskDrawer';
import { AssigneeSelect } from './AssigneeSelect';
import { DatePicker } from './DatePicker';
import { PrioritySelect } from './PrioritySelect';
import { StatusSelect } from './StatusSelect';
import './taskDetail.css';

const fileSize = (n: number | null) =>
  n == null ? '' : n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;

const stamp = (iso: string) =>
  new Date(iso).toLocaleString(document.documentElement.lang === 'de' ? 'de-DE' : 'en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

const show = (v: unknown) => (v == null || v === '' ? '—' : Array.isArray(v) ? v.join(', ') || '—' : String(v));

const changeText = (field: string, [from, to]: [unknown, unknown], t: (s: string) => string) =>
  `${t(field.replace(/_/g, ' '))}: ${show(from)} → ${show(to)}`;

const parseLabels = (text: string) => [...new Set(text.split(',').map((l) => l.trim()).filter(Boolean))];

function Row({ label, children }: { label: string; children: ReactNode }) {
  const { t } = usePrefs();
  return (
    <div className="td-row">
      <label>{t(label)}</label>
      {children}
    </div>
  );
}

function Description({ value, onChange, readOnly }: { value: string; onChange: (d: string) => void; readOnly?: boolean }) {
  const { t } = usePrefs();
  if (readOnly) return <p className="td-desc-static">{value || t('No description added.')}</p>;
  return (
    <textarea
      className="td-desc"
      aria-label={t('Description')}
      placeholder={t('Add a description and acceptance criteria')}
      rows={6}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

/** Opens from the Task List (Figma "PM · Related Task · Added"). Edits are staged and sent together by the Save button via PATCH /tasks/{id}. */
export function TaskDetailPage() {
  const { t } = usePrefs();
  const { taskId = '' } = useParams();
  const { user } = useAuth();
  const { data: task, isPending, isError, refetch } = useTask(taskId);
  const statuses = useProjectStatuses(task?.project_id);
  const toast = useToast();
  const update = useUpdateTask(task);
  const attachments = useAttachments(taskId);
  const files = useAttachmentActions(taskId);
  const comments = useComments(taskId);
  const activity = useActivity(taskId);
  const addComment = useAddComment(taskId);
  const [comment, setComment] = useState('');
  const picker = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState('');
  // Attachments save as soon as they are picked, but the Save button stays active so the page can be confirmed.
  const [filesChanged, setFilesChanged] = useState(false);
  const [drawer, setDrawer] = useState(false);
  // No relations endpoint yet: kept in page state until the backend adds one.
  const [related, setRelated] = useState<{ relation: Relationship; task: Task }[]>([]);
  // Unsaved edits, sent together by the Save button.
  const [draft, setDraft] = useState<TaskPatch>({});
  // Raw text of the labels input while a PM edits it; null shows the saved labels.
  const [labelText, setLabelText] = useState<string | null>(null);

  if (isPending)
    return (
      <section className="page-body">
        <LoadingState title="Loading task" />
      </section>
    );
  if (isError || !task)
    return (
      <section className="page-body">
        <ErrorState
          title="We couldn’t load this task"
          text="It may not exist, or you may not have access."
          onRetry={() => void refetch()}
        />
      </section>
    );

  const stage = (patch: TaskPatch) => setDraft((d) => ({ ...d, ...patch }));
  const saved: TaskPatch = {
    description: task.description,
    priority: task.priority,
    status_id: task.status.id,
    assignee_id: task.assignee?.id ?? null,
    start_date: task.start_date,
    due_date: task.due_date,
    estimate_value: task.estimate_value,
    estimate_unit: task.estimate_unit,
    blocked_reason: task.blocked_reason,
    labels: task.labels,
  };
  // Mirrors the backend: only a PM edits task details; a developer changes the status of their own tasks.
  const isPm = user?.role === 'pm';
  // A developer may also move the dates of a task they created for themselves.
  const canSchedule = isPm || (task.assignee?.id === user?.id && task.reporter.id === user?.id);
  const changes: TaskPatch = {};
  for (const key of Object.keys(draft) as (keyof TaskPatch)[]) {
    // The backend rejects a developer's PATCH that carries PM-only fields, so Save sends just status fields for them.
    if (!isPm && key !== 'status_id' && key !== 'blocked_reason' && !(canSchedule && (key === 'start_date' || key === 'due_date'))) continue;
    const next =
      key === 'description' ? draft.description?.trim() || null : key === 'blocked_reason' ? draft.blocked_reason?.trim() || null : draft[key];
    if (JSON.stringify(next) !== JSON.stringify(saved[key])) Object.assign(changes, { [key]: next });
  }
  const dirty = Object.keys(changes).length > 0;
  // A blocked status needs a reason (the backend rejects it otherwise).
  const targetStatus = (statuses.data ?? [task.status]).find((s) => s.id === (draft.status_id ?? task.status.id)) ?? task.status;
  const blocking = targetStatus.category === 'blocked';
  const reason = (draft.blocked_reason !== undefined ? draft.blocked_reason : task.blocked_reason) ?? '';
  const missingReason = blocking && !reason.trim();
  const save = () => {
    if (!dirty) {
      setFilesChanged(false);
      return;
    }
    // The reason travels with the status change that needs it, even when the task already had one.
    if (blocking && changes.status_id && !('blocked_reason' in changes)) changes.blocked_reason = reason.trim();
    update.mutate(changes, {
      onSuccess: () => {
        setDraft({});
        setLabelText(null);
        setFilesChanged(false);
      },
      onError: (e) => toast.error(describeApiError(e, t('Could not save your change.'))),
    });
  };
  const view = {
    description: draft.description !== undefined ? (draft.description ?? '') : (task.description ?? ''),
    priority: draft.priority ?? task.priority,
    status_id: draft.status_id ?? task.status.id,
    assignee_id: draft.assignee_id !== undefined ? draft.assignee_id : (task.assignee?.id ?? null),
    start_date: draft.start_date !== undefined ? draft.start_date : task.start_date,
    due_date: draft.due_date !== undefined ? draft.due_date : task.due_date,
  };
  const estimate = {
    value: draft.estimate_value !== undefined ? draft.estimate_value : task.estimate_value,
    unit: draft.estimate_unit !== undefined ? draft.estimate_unit : task.estimate_unit,
  };
  const canStatus = isPm || task.assignee?.id === user?.id;
  // PMs stage edits for the Save button; developers apply each change straight away, as they do for status.
  const edit = (patch: TaskPatch) =>
    isPm ? stage(patch) : update.mutate(patch, { onError: (e) => toast.error(describeApiError(e, t('Could not save your change.'))) });
  const conflict = update.error instanceof ApiError && update.error.status === 409;

  return (
    <section className={isPm ? 'page-body task-detail' : 'page-body task-detail td-dev'}>
      <p className="td-crumb">
        <Link to={paths.project(task.project_id)}>{task.project_name}</Link> /{' '}
        {isPm ? <Link to={paths.tasks}>{t('Task List')}</Link> : <Link to={paths.projectBoard(task.project_id)}>{t('Board')}</Link>} / {task.key}
      </p>
      <div className="td-head">
        <h2 className="td-title">{task.title}</h2>
        <button type="button" className="btn" disabled={(!dirty && !filesChanged) || missingReason || update.isPending} onClick={save}>
          {t(update.isPending ? 'Saving…' : 'Save')}
        </button>
      </div>
      {isPm && (
        <p className="td-meta">
          {task.key} · {t('Updated')} {stamp(task.updated_at)}
          {update.isPending && ` · ${t('Saving…')}`}
          {!dirty && update.isSuccess && ` · ✓ ${t('Saved')}`}
        </p>
      )}
      {update.isError && (
        <p className="td-error" role="alert">
          {conflict ? t('Someone else changed this task. The latest version has been loaded; try again.') : describeApiError(update.error, t('Could not save your change.'))}
        </p>
      )}

      <div className="td-grid">
        <div className="td-col">
          <section className="td-card">
            <h3>{t('Description')}</h3>
            <p className="td-sub">{t('Task context and acceptance criteria')}</p>
            {isPm && <p className="td-hint">{t('Click the text to edit · press Save to apply your changes')}</p>}
            <Description value={view.description} readOnly={!isPm} onChange={(description) => stage({ description })} />
            <div className="td-attach">
              <strong>
                {t('Attachments')} · {attachments.data?.length ?? 0} {t(attachments.data?.length === 1 ? 'file' : 'files')}
              </strong>
              {(attachments.data ?? []).map((a) => (
                <div key={a.id} className="td-file">
                  {a.kind === 'link' ? (
                    <a href={a.url ?? '#'} target="_blank" rel="noreferrer noopener">{a.name}</a>
                  ) : (
                    <button type="button" className="td-link" onClick={() => downloadAttachment(a).catch(() => setFileError(t('Could not download the file.')))}>
                      {a.name}
                    </button>
                  )}
                  <span>{fileSize(a.size_bytes)}</span>
                  {/* The backend only lets the uploader or a PM delete an attachment. */}
                  {(isPm || a.uploaded_by.id === user?.id) && (
                    <button
                      type="button"
                      className="td-link"
                      aria-label={t('Remove {name}', { name: a.name })}
                      disabled={files.remove.isPending}
                      onClick={() =>
                        files.remove.mutate(a.id, {
                          onSuccess: () => setFilesChanged(true),
                          onError: (e) => setFileError(describeApiError(e, t('Could not remove the file.'))),
                        })
                      }
                    >
                      {t('Remove')}
                    </button>
                  )}
                </div>
              ))}
              <input
                ref={picker}
                type="file"
                accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.ppt,.pptx,.txt,.md,.rtf,.odt,.ods,.png,.jpg,.jpeg,.gif,.webp,.mp3,.m4a,.wav,.ogg,.opus,.aac,.weba"
                multiple
                hidden
                onChange={(e) => {
                  const picked = Array.from(e.target.files ?? []);
                  e.target.value = '';
                  if (!picked.length) return;
                  setFileError('');
                  files.upload.mutate(picked, {
                    onSuccess: () => setFilesChanged(true),
                    onError: (err) =>
                      setFileError(err instanceof ApiError && err.status === 413 ? t('That file is too large (25 MB max).') : describeApiError(err, t('Could not upload the file.'))),
                  });
                }}
              />
              <button type="button" className="td-outline" disabled={files.upload.isPending} onClick={() => picker.current?.click()}>
                {t(files.upload.isPending ? 'Uploading…' : '+ Attach files')}
              </button>
              {fileError && (
                <p className="td-error" role="alert">
                  {fileError}
                </p>
              )}
            </div>
          </section>

          <section className="td-card">
            <h3>{t('Activity & audit log')}</h3>
            <p className="td-sub">{t('Comments and updates')}</p>
            {comments.data?.length ? (
              <ul className="td-comments">
                {comments.data.map((c) => (
                  <li key={c.id}>
                    <strong>{c.author.name}</strong> <span>{stamp(c.created_at)}</span>
                    <p>{c.body}</p>
                  </li>
                ))}
              </ul>
            ) : (
              !activity.data?.items.length && <p className="td-none">{t('No comments yet.')}</p>
            )}
            {activity.data?.items.length ? (
              <ul className="td-comments td-history">
                {activity.data.items.map((a) => (
                  <li key={a.id}>
                    <strong>{a.actor.name}</strong> {t(a.action.replace(/_/g, ' '))} <span>{stamp(a.created_at)}</span>
                    {Object.entries(a.changes).map(([field, change]) => (
                      <p key={field}>{changeText(field, change, t)}</p>
                    ))}
                  </li>
                ))}
              </ul>
            ) : activity.isError ? (
              <p className="td-empty">{t('History could not be loaded.')}</p>
            ) : (
              isPm && !comments.data?.length && !activity.isPending && <p className="td-empty">{t('No activity recorded yet.')}</p>
            )}
            <form
              className="td-composer"
              onSubmit={(e) => {
                e.preventDefault();
                const body = comment.trim();
                if (!body) return;
                addComment.mutate(body, {
                  onSuccess: () => setComment(''),
                  onError: () => toast.error(t('Could not post your comment.')),
                });
              }}
            >
              <input
                aria-label={t('Add a comment')}
                placeholder={t('Add a comment…')}
                maxLength={5000}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
              <button type="submit" className="btn" disabled={!comment.trim() || addComment.isPending}>
                {t(addComment.isPending ? 'Sending…' : 'Send')}
              </button>
            </form>
          </section>
        </div>

        <div className="td-col">
          <section className="td-card">
            <h3>{t('Task details')}</h3>
            <p className="td-sub">{t(isPm ? 'Ownership, schedule, and priority' : update.isPending ? 'Saving…' : dirty ? 'Unsaved changes' : 'Saved')}</p>
            <Row label="Task status">
              {canStatus ? (
                <StatusSelect
                  value={view.status_id}
                  options={statuses.data ?? [task.status]}
                  onChange={(status_id) => {
                    // Developers apply a status straight away; a blocked status first needs its reason, which Save sends.
                    const next = (statuses.data ?? []).find((s) => s.id === status_id);
                    if (isPm || next?.category === 'blocked') return stage({ status_id });
                    update.mutate(
                      { status_id },
                      {
                        // Drop any staged blocked choice so the dropdown shows the saved status.
                        onSuccess: () => setDraft((d) => ({ ...d, status_id: undefined, blocked_reason: undefined })),
                        onError: (e) => toast.error(describeApiError(e, t('Could not save your change.'))),
                      },
                    );
                  }}
                />
              ) : (
                <span className="td-static">{t(task.status.name)}</span>
              )}
            </Row>
            {blocking && (
              <Row label="Blocked reason">
                {canStatus ? (
                  <input
                    aria-label={t('Blocked reason')}
                    aria-invalid={missingReason}
                    placeholder={t('Why is this blocked?')}
                    value={reason}
                    onChange={(e) => stage({ blocked_reason: e.target.value })}
                  />
                ) : (
                  <span className="td-static">{task.blocked_reason || '—'}</span>
                )}
              </Row>
            )}
            <Row label="Priority">
              <PrioritySelect value={view.priority} onChange={(priority) => edit({ priority })} />
            </Row>
            <Row label="Assignee">
              {isPm ? (
                <AssigneeSelect value={view.assignee_id} current={task.assignee} onChange={(assignee_id) => edit({ assignee_id })} />
              ) : (
                <span className="td-static">{task.assignee?.name || t('Unassigned')}</span>
              )}
            </Row>
            <Row label="Reporter">
              <span className="td-static">{task.reporter.name || '—'}</span>
            </Row>
            <Row label="Start date">
              {canSchedule ? (              <DatePicker
                  label="Start date"
                  value={view.start_date}
                  max={view.due_date}
                  hint="Start date must be on or before due date."
                  error="Pick a date on or before the due date."
                  onChange={(start_date) => edit({ start_date })}
                />
              
              ) : (
                <span className="td-static">{view.start_date ? formatDate(view.start_date) : '—'}</span>
              )}
            </Row>
            <Row label="Due date">
              {canSchedule ? (              <DatePicker
                  label="Due date"
                  value={view.due_date}
                  min={view.start_date}
                  hint="Due date must be on or after start date."
                  error="Pick a date on or after the start date."
                  onChange={(due_date) => edit({ due_date })}
                />
              
              ) : (
                <span className="td-static">{view.due_date ? formatDate(view.due_date) : '—'}</span>
              )}
            </Row>
            <Row label="Estimate">
              {isPm ? (
                <span className="td-estimate">
                  <input
                    type="number"
                    min={1}
                    step={1}
                    aria-label={t('Estimate amount')}
                    value={estimate.value ?? ''}
                    onChange={(e) => {
                      const n = Math.floor(Number(e.target.value));
                      // Amount and unit travel together: clearing one clears the other.
                      stage(e.target.value === '' || n < 1 ? { estimate_value: null, estimate_unit: null } : { estimate_value: n, estimate_unit: estimate.unit ?? 'hours' });
                    }}
                  />
                  <select
                    aria-label={t('Estimate unit')}
                    value={estimate.unit ?? 'hours'}
                    disabled={estimate.value == null}
                    onChange={(e) => stage({ estimate_unit: e.target.value as EstimateUnit })}
                  >
                    {ESTIMATE_UNITS.map((u) => (
                      <option key={u} value={u}>
                        {t(u)}
                      </option>
                    ))}
                  </select>
                </span>
              ) : (
                <span className="td-static">{task.estimate_value != null ? `${task.estimate_value} ${t(task.estimate_unit ?? '')}` : '—'}</span>
              )}
            </Row>
            <Row label="Labels">
              {isPm ? (
                <input
                  aria-label={t('Labels')}
                  placeholder={t('Comma-separated labels')}
                  value={labelText ?? task.labels.join(', ')}
                  onChange={(e) => {
                    setLabelText(e.target.value);
                    stage({ labels: parseLabels(e.target.value) });
                  }}
                />
              ) : (
                <span className="td-static">{task.labels.join(' · ') || '—'}</span>
              )}
            </Row>
          </section>

          <section className="td-card">
            <div className="td-card-head">
              <h3>{t('Related tasks')}</h3>
              {isPm ? (
                <button type="button" className="btn td-relate" onClick={() => setDrawer(true)}>
                  {t('Related Task')}
                </button>
              ) : (
                <button type="button" className="btn td-relate" onClick={() => setDrawer(true)}>
                  {t('Relate Task')}
                </button>
              )}
            </div>
            {isPm && related.length === 0 && <p className="td-empty">{t('No related tasks.')}</p>}
            {related.map((r) => (
              <div key={`${r.relation}-${r.task.id}`} className="td-related">
                <Link to={paths.task(r.task.id)}>
                  {r.task.key} · {r.task.title}
                </Link>
                <span>
                  {t(relationLabels[r.relation])} · {t(r.task.status.name)}
                </span>
              </div>
            ))}
          </section>
        </div>
      </div>
      {drawer && (
        <RelatedTaskDrawer
          task={task}
          onClose={() => setDrawer(false)}
          onAdd={(relation, other) => {
            setRelated((prev) =>
              prev.some((r) => r.task.id === other.id && r.relation === relation) ? prev : [...prev, { relation, task: other }],
            );
            setDrawer(false);
          }}
        />
      )}
    </section>
  );
}
