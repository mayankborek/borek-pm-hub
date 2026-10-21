import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { formatDate } from '@/features/projects/projectUi';
import { ApiError } from '@/shared/api/client';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import {
  downloadAttachment,
  useAttachmentActions,
  useAttachments,
  useProjectMembers,
  useProjectStatuses,
  useTask,
  useUpdateTask,
  type Task,
  type TaskDetail,
} from './tasksApi';
import { RelatedTaskDrawer, relationLabels, type Relationship } from './RelatedTaskDrawer';
import { AssigneeSelect } from './AssigneeSelect';
import { DatePicker } from './DatePicker';
import { PriorityIndicator, PrioritySelect } from './PrioritySelect';
import { StatusSelect } from './StatusSelect';
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

function Description({ task, save, readOnly }: { task: TaskDetail; save: (d: string | null) => void; readOnly?: boolean }) {
  const [text, setText] = useState(task.description ?? '');
  useEffect(() => setText(task.description ?? ''), [task.description]);
  if (readOnly) return <p className="td-desc-static">{task.description || 'No description.'}</p>;
  return (
    <textarea
      className="td-desc"
      aria-label="Description"
      placeholder="Add a description and acceptance criteria"
      rows={6}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => text !== (task.description ?? '') && save(text.trim() || null)}
    />
  );
}

/** Opens from the Task List (Figma "PM · Related Task · Added"). Fields save on change via PATCH /tasks/{id}. */
export function TaskDetailPage() {
  const { taskId = '' } = useParams();
  const { user } = useAuth();
  const { data: task, isPending, isError, refetch } = useTask(taskId);
  const statuses = useProjectStatuses(task?.project_id);
  const members = useProjectMembers(task?.project_id);
  const update = useUpdateTask(task);
  const attachments = useAttachments(taskId);
  const files = useAttachmentActions(taskId);
  const picker = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState('');
  const [drawer, setDrawer] = useState(false);
  // No relations endpoint yet: kept in page state until the backend adds one.
  const [related, setRelated] = useState<{ relation: Relationship; task: Task }[]>([]);
  const [labels, setLabels] = useState('');
  useEffect(() => setLabels(task?.labels.join(', ') ?? ''), [task?.labels]);

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

  const save = update.mutate;
  // Mirrors the backend: only a PM edits task details; a developer changes the status of their own tasks.
  const isPm = user?.role === 'pm';
  const canStatus = isPm || task.assignee?.id === user?.id;
  const conflict = update.error instanceof ApiError && update.error.status === 409;

  return (
    <section className="page-body task-detail">
      <p className="td-crumb">
        <Link to={paths.project(task.project_id)}>{task.project_name}</Link> /{' '}
        {isPm ? <Link to={paths.tasks}>Task List</Link> : <Link to={paths.projectBoard(task.project_id)}>Board</Link>} / {task.key}
      </p>
      <h2 className="td-title">{task.title}</h2>
      <p className="td-meta">
        {task.key} · Updated {stamp(task.updated_at)}
        {update.isPending && ' · Saving…'}
        {update.isSuccess && ' · ✓ Saved'}
      </p>
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
            {isPm && <p className="td-hint">Click the text to edit · saves when you leave the field</p>}
            <Description task={task} save={(description) => save({ description })} readOnly={!isPm} />
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
            <p className="td-empty">No activity recorded yet.</p>
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
            <p className="td-sub">Ownership, schedule, and priority</p>
            <Row label="Status">
              {canStatus ? (
                <StatusSelect
                  value={task.status.id}
                  options={statuses.data ?? [task.status]}
                  onChange={(status_id) => save({ status_id })}
                />
              ) : (
                <span className="td-static">{task.status.name}</span>
              )}
            </Row>
            <Row label="Priority">
              {isPm ? (
                <PrioritySelect value={task.priority} onChange={(priority) => save({ priority })} />
              ) : (
                <span className="td-static">
                  <PriorityIndicator priority={task.priority} />
                </span>
              )}
            </Row>
            <Row label="Assignee">
              {isPm ? (
                <AssigneeSelect
                  value={task.assignee?.id ?? null}
                  current={task.assignee}
                  members={members.data ?? []}
                  onChange={(assignee_id) => save({ assignee_id })}
                />
              ) : (
                <span className="td-static">{task.assignee?.name ?? 'Unassigned'}</span>
              )}
            </Row>
            <Row label="Reporter">
              <span className="td-static">{task.reporter.name}</span>
            </Row>
            <Row label="Start date">
              {isPm ? (
                <DatePicker
                  label="Start date"
                  value={task.start_date}
                  max={task.due_date}
                  hint="Start date must be on or before due date."
                  error="Pick a date on or before the due date."
                  onChange={(start_date) => save({ start_date })}
                />
              ) : (
                <span className="td-static">{formatDate(task.start_date)}</span>
              )}
            </Row>
            <Row label="Due date">
              {isPm ? (
                <DatePicker
                  label="Due date"
                  value={task.due_date}
                  min={task.start_date}
                  hint="Due date must be on or after start date."
                  error="Pick a date on or after the start date."
                  onChange={(due_date) => save({ due_date })}
                />
              ) : (
                <span className="td-static">{formatDate(task.due_date)}</span>
              )}
            </Row>
            <Row label="Labels">
              {!isPm ? (
                <span className="td-static">{task.labels.join(' · ') || '—'}</span>
              ) : (
              <input
                aria-label="Labels"
                placeholder="Comma-separated"
                value={labels}
                onChange={(e) => setLabels(e.target.value)}
                onBlur={() => {
                  const next = labels
                    .split(',')
                    .map((l) => l.trim())
                    .filter(Boolean);
                  if (next.join('|') !== task.labels.join('|')) save({ labels: next });
                }}
              />
              )}
            </Row>
          </section>

          <section className="td-card">
            <div className="td-card-head">
              <h3>Related tasks</h3>
              <button type="button" className="td-outline" onClick={() => setDrawer(true)}>
                Related Task
              </button>
            </div>
            {related.length === 0 && <p className="td-empty">No related tasks.</p>}
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
