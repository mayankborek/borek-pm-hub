import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { ApiError } from '@/shared/api/client';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import {
  useProjectMembers,
  useProjectStatuses,
  useTask,
  useUpdateTask,
  type TaskDetail,
  type TaskPriority,
} from './tasksApi';
import './taskDetail.css';

const PRIORITIES: { value: TaskPriority; label: string }[] = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

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

function Description({ task, save }: { task: TaskDetail; save: (d: string | null) => void }) {
  const [text, setText] = useState(task.description ?? '');
  useEffect(() => setText(task.description ?? ''), [task.description]);
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
  const { data: task, isPending, isError, refetch } = useTask(taskId);
  const statuses = useProjectStatuses(task?.project_id);
  const members = useProjectMembers(task?.project_id);
  const update = useUpdateTask(task);
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
  const conflict = update.error instanceof ApiError && update.error.status === 409;

  return (
    <section className="page-body task-detail">
      <p className="td-crumb">
        <Link to={paths.project(task.project_id)}>{task.project_name}</Link> / <Link to={paths.tasks}>Task List</Link> /{' '}
        {task.key}
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
            <p className="td-hint">Click the text to edit · saves when you leave the field</p>
            <Description task={task} save={(description) => save({ description })} />
            <div className="td-attach">
              <strong>Attachments · 0 files</strong>
              <button type="button" className="td-outline" disabled title="File attachments are not available yet">
                + Attach files
              </button>
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
              <select value={task.status.id} aria-label="Status" onChange={(e) => save({ status_id: e.target.value })}>
                {(statuses.data ?? [task.status]).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Row>
            <Row label="Priority">
              <select
                value={task.priority}
                aria-label="Priority"
                onChange={(e) => save({ priority: e.target.value as TaskPriority })}
              >
                {PRIORITIES.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </Row>
            <Row label="Assignee">
              <select
                value={task.assignee?.id ?? ''}
                aria-label="Assignee"
                onChange={(e) => save({ assignee_id: e.target.value || null })}
              >
                <option value="">Unassigned</option>
                {(members.data ?? []).map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </Row>
            <Row label="Reporter">
              <span className="td-static">{task.reporter.name}</span>
            </Row>
            <Row label="Start date">
              <input
                type="date"
                aria-label="Start date"
                value={task.start_date ?? ''}
                onChange={(e) => save({ start_date: e.target.value || null })}
              />
            </Row>
            <Row label="Due date">
              <input
                type="date"
                aria-label="Due date"
                value={task.due_date ?? ''}
                onChange={(e) => save({ due_date: e.target.value || null })}
              />
            </Row>
            <Row label="Labels">
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
            </Row>
          </section>

          <section className="td-card">
            <div className="td-card-head">
              <h3>Related tasks</h3>
              <button type="button" className="td-outline" disabled title="Task relations are not available yet">
                Related Task
              </button>
            </div>
            <p className="td-empty">No related tasks.</p>
          </section>
        </div>
      </div>
    </section>
  );
}
