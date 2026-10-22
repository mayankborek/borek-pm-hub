import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { ApiError } from '@/shared/api/client';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import {
  downloadAttachment,
  useAttachmentActions,
  useAttachments,
  useProjectStatuses,
  useTask,
  useUpdateTask,
  type Task,
  type TaskPatch,
} from './tasksApi';
import { RelatedTaskDrawer, relationLabels, type Relationship } from './RelatedTaskDrawer';
import { AssigneeSelect } from './AssigneeSelect';
import { DatePicker } from './DatePicker';
import { PrioritySelect } from './PrioritySelect';
import { StatusSelect } from './StatusSelect';
import chevronIcon from './assets/select-chevron.svg';
import './taskDetail.css';

const fileSize = (n: number | null) =>
  n == null ? '' : n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;

const stamp = (iso: string) =>
  new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="td-row">
      <label>{label}</label>
      {children}
    </div>
  );
}

/** Read-only value in the select styling of the developer design (Figma "Select · Priority" etc.). */
function Field({ children, icon = chevronIcon }: { children: ReactNode; icon?: string }) {
  return (
    <span className="td-field">
      <span>{children}</span>
      <img src={icon} alt="" width={16} height={16} />
    </span>
  );
}

function Description({ value, onChange, readOnly }: { value: string; onChange: (d: string) => void; readOnly?: boolean }) {
  if (readOnly) return <p className="td-desc-static">{value || 'No description added.'}</p>;
  return (
    <textarea
      className="td-desc"
      aria-label="Description"
      placeholder="Add a description and acceptance criteria"
      rows={6}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

/** Opens from the Task List (Figma "PM · Related Task · Added"). Edits are staged and sent together by the Save button via PATCH /tasks/{id}. */
export function TaskDetailPage() {
  const { taskId = '' } = useParams();
  const { user } = useAuth();
  const { data: task, isPending, isError, refetch } = useTask(taskId);
  const statuses = useProjectStatuses(task?.project_id);
  const toast = useToast();
  const update = useUpdateTask(task);
  const attachments = useAttachments(taskId);
  const files = useAttachmentActions(taskId);
  const picker = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState('');
  const [drawer, setDrawer] = useState(false);
  // No relations endpoint yet: kept in page state until the backend adds one.
  const [related, setRelated] = useState<{ relation: Relationship; task: Task }[]>([]);
  // Unsaved edits, sent together by the Save button.
  const [draft, setDraft] = useState<TaskPatch>({});
  const [labels, setLabels] = useState('');
  const confirmedLabels = useRef('');
  useEffect(() => {
    const next = task?.labels.join(', ') ?? '';
    setLabels((draft) => (draft === confirmedLabels.current ? next : draft));
    confirmedLabels.current = next;
  }, [task?.labels]);

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
  const parsedLabels = labels
    .split(',')
    .map((l) => l.trim())
    .filter(Boolean);
  const saved: TaskPatch = {
    description: task.description,
    priority: task.priority,
    status_id: task.status.id,
    assignee_id: task.assignee?.id ?? null,
    start_date: task.start_date,
    due_date: task.due_date,
    progress: task.progress,
    blocked_reason: task.blocked_reason,
  };
  const changes: TaskPatch = {};
  for (const key of Object.keys(draft) as (keyof TaskPatch)[]) {
    const next =
      key === 'description' ? draft.description?.trim() || null : key === 'blocked_reason' ? draft.blocked_reason?.trim() || null : draft[key];
    if (next !== saved[key]) Object.assign(changes, { [key]: next });
  }
  if (parsedLabels.join('|') !== task.labels.join('|')) changes.labels = parsedLabels;
  const dirty = Object.keys(changes).length > 0;
  // A blocked status needs a reason (the backend rejects it otherwise).
  const targetStatus = (statuses.data ?? [task.status]).find((s) => s.id === (draft.status_id ?? task.status.id)) ?? task.status;
  const blocking = targetStatus.category === 'blocked';
  const reason = (draft.blocked_reason !== undefined ? draft.blocked_reason : task.blocked_reason) ?? '';
  const missingReason = blocking && !reason.trim();
  const save = () => {
    // The reason travels with the status change that needs it, even when the task already had one.
    if (blocking && changes.status_id && !('blocked_reason' in changes)) changes.blocked_reason = reason.trim();
    update.mutate(changes, {
      onSuccess: () => setDraft({}),
      onError: (e) =>
        toast.error(e instanceof ApiError && e.status === 409 ? 'Someone else changed this task. Your edit was not saved.' : 'Could not save your change.'),
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
  // Mirrors the backend: only a PM edits task details; a developer changes the status of their own tasks.
  const isPm = user?.role === 'pm';
  const canStatus = isPm || task.assignee?.id === user?.id;
  // PMs stage edits for the Save button; developers apply each change straight away, as they do for status.
  const edit = (patch: TaskPatch) =>
    isPm ? stage(patch) : update.mutate(patch, { onError: () => toast.error('Could not save your change.') });
  const conflict = update.error instanceof ApiError && update.error.status === 409;

  return (
    <section className={isPm ? 'page-body task-detail' : 'page-body task-detail td-dev'}>
      <p className="td-crumb">
        <Link to={paths.project(task.project_id)}>{task.project_name}</Link> /{' '}
        {isPm ? <Link to={paths.tasks}>Task List</Link> : <Link to={paths.projectBoard(task.project_id)}>Board</Link>} / {task.key}
      </p>
      <div className="td-head">
        <h2 className="td-title">{task.title}</h2>
        <button type="button" className="btn" disabled={!dirty || missingReason || update.isPending} onClick={save}>
          {update.isPending ? 'Saving…' : 'Save'}
        </button>
      </div>
      {isPm && (
        <p className="td-meta">
          {task.key} · Updated {stamp(task.updated_at)}
          {update.isPending && ' · Saving…'}
          {!dirty && update.isSuccess && ' · ✓ Saved'}
          {dirty && ' · Unsaved changes'}
        </p>
      )}
      {update.isError && (
        <p className="td-error" role="alert">
          {conflict ? 'Someone else changed this task. The latest version has been loaded; try again.' : 'Could not save your change.'}
        </p>
      )}

      <div className="td-grid">
        <div className="td-col">
          <section className="td-card">
            <h3>Description</h3>
            <p className="td-sub">Task context and acceptance criteria</p>
            <p className="td-hint">Click the text to edit · press Save to apply your changes</p>
            <Description value={view.description} onChange={(description) => stage({ description })} />
            <div className="td-attach">
              <strong>
                Attachments · {attachments.data?.length ?? 0} {attachments.data?.length === 1 ? 'file' : 'files'}
              </strong>
              {(attachments.data ?? []).map((a) => (
                <div key={a.id} className="td-file">
                  {a.kind === 'link' ? (
                    <a href={a.url ?? '#'} target="_blank" rel="noreferrer noopener">{a.name}</a>
                  ) : (
                    <button type="button" className="td-link" onClick={() => downloadAttachment(a).catch(() => setFileError('Could not download the file.'))}>
                      {a.name}
                    </button>
                  )}
                  <span>{fileSize(a.size_bytes)}</span>
                  <button
                    type="button"
                    className="td-link"
                    aria-label={`Remove ${a.name}`}
                    disabled={files.remove.isPending}
                    onClick={() => files.remove.mutate(a.id, { onError: () => setFileError('Could not remove the file.') })}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <input
                ref={picker}
                type="file"
                multiple
                hidden
                onChange={(e) => {
                  const picked = Array.from(e.target.files ?? []);
                  e.target.value = '';
                  if (!picked.length) return;
                  setFileError('');
                  files.upload.mutate(picked, {
                    onError: (err) =>
                      setFileError(err instanceof ApiError && err.status === 413 ? 'That file is too large.' : 'Could not upload the file.'),
                  });
                }}
              />
              <button type="button" className="td-outline" disabled={files.upload.isPending} onClick={() => picker.current?.click()}>
                {files.upload.isPending ? 'Uploading…' : '+ Attach files'}
              </button>
              {fileError && (
                <p className="td-error" role="alert">
                  {fileError}
                </p>
              )}
            </div>
          </section>

          <section className="td-card">
            <h3>Activity &amp; audit log</h3>
            <p className="td-sub">Comments and updates</p>
            {isPm ? <p className="td-empty">No activity recorded yet.</p> : <p className="td-none">No comments yet.</p>}
            <div className="td-composer">
              <input aria-label="Add a comment" placeholder="Add a comment…" disabled />
              <button type="button" className="btn" disabled>
                Send
              </button>
            </div>
          </section>
        </div>

        <div className="td-col">
          <section className="td-card">
            <h3>Task details</h3>
            <p className="td-sub">{isPm ? 'Ownership, schedule, and priority' : update.isPending ? 'Saving…' : dirty ? 'Unsaved changes' : 'Saved'}</p>
            <Row label="Status">
              {canStatus ? (
                <StatusSelect
                  value={view.status_id}
                  options={statuses.data ?? [task.status]}
                  onChange={(status_id) => {
                    // Developers apply a status straight away; a blocked status first needs its reason, which Save sends.
                    const next = (statuses.data ?? []).find((s) => s.id === status_id);
                    if (isPm || next?.category === 'blocked') return stage({ status_id });
                    update.mutate({ status_id }, { onError: () => toast.error('Could not save your change.') });
                  }}
                />
              ) : (
                <span className="td-static">{task.status.name}</span>
              )}
            </Row>
            {blocking && (
              <Row label="Blocked reason">
                {canStatus ? (
                  <input
                    aria-label="Blocked reason"
                    aria-invalid={missingReason}
                    placeholder="Why is this blocked?"
                    value={reason}
                    onChange={(e) => stage({ blocked_reason: e.target.value })}
                  />
                ) : (
                  <span className="td-static">{task.blocked_reason || '—'}</span>
                )}
              </Row>
            )}
            {isPm && (
            <Row label="Progress">
              {canStatus ? (
                <input
                  type="number"
                  min={0}
                  max={100}
                  aria-label="Progress (%)"
                  value={draft.progress ?? task.progress}
                  onChange={(e) => stage({ progress: Math.max(0, Math.min(100, Math.round(Number(e.target.value) || 0))) })}
                />
              ) : (
                <span className="td-static">{task.progress}%</span>
              )}
            </Row>
            )}
            <Row label="Priority">
              <PrioritySelect value={view.priority} onChange={(priority) => edit({ priority })} />
            </Row>
            <Row label="Assignee">
              <AssigneeSelect value={view.assignee_id} current={task.assignee} onChange={(assignee_id) => edit({ assignee_id })} />
            </Row>
            <Row label="Reporter">
              {isPm ? <span className="td-static">{task.reporter.name}</span> : <Field>{task.reporter.name || '—'}</Field>}
            </Row>
            <Row label="Start date">
              <DatePicker
                label="Start date"
                value={view.start_date}
                max={view.due_date}
                hint="Start date must be on or before due date."
                error="Pick a date on or before the due date."
                onChange={(start_date) => edit({ start_date })}
              />
            </Row>
            <Row label="Due date">
              <DatePicker
                label="Due date"
                value={view.due_date}
                min={view.start_date}
                hint="Due date must be on or after start date."
                error="Pick a date on or after the start date."
                onChange={(due_date) => edit({ due_date })}
              />
            </Row>
            {!isPm && (
              <Row label="Estimate">
                <Field>—</Field>
              </Row>
            )}
            <Row label="Labels">
              {!isPm ? (
                <Field>{task.labels.join(' · ') || '—'}</Field>
              ) : (
              <input
                aria-label="Labels"
                placeholder="Comma-separated"
                value={labels}
                onChange={(e) => setLabels(e.target.value)}
              />
              )}
            </Row>
          </section>

          <section className="td-card">
            <div className="td-card-head">
              <h3>Related tasks</h3>
              {isPm ? (
                <button type="button" className="td-outline" onClick={() => setDrawer(true)}>
                  Related Task
                </button>
              ) : (
                <button type="button" className="btn td-relate" onClick={() => setDrawer(true)}>
                  Relate Task
                </button>
              )}
            </div>
            {isPm && related.length === 0 && <p className="td-empty">No related tasks.</p>}
            {related.map((r) => (
              <div key={`${r.relation}-${r.task.id}`} className="td-related">
                <Link to={paths.task(r.task.id)}>
                  {r.task.key} · {r.task.title}
                </Link>
                <span>
                  {relationLabels[r.relation]} · {r.task.status.name}
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
