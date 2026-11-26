import { useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { ApiError, api, describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import {
  downloadAttachment,
  useActivity,
  useAddComment,
  useAttachmentActions,
  useAttachments,
  useComments,
  useEditComment,
  useProjectMembers,
  useProjectStatuses,
  useTask,
  useUpdateTask,
  type Task,
  type TaskPatch,
  type TaskPriority,
} from '@/features/tasks/tasksApi';
import { DatePicker } from '@/features/tasks/DatePicker';
import { MentionInput, mentionIdsFor } from '@/features/tasks/MentionInput';
import { RelatedTaskDrawer, relationLabels, type Relationship } from '@/features/tasks/RelatedTaskDrawer';
import { PRIORITIES, PRIORITY_LABEL } from '@/features/accountManager/amWork';
import '@/features/tasks/taskDetail.css';
import { Dropdown, fmtDate, statusTone } from './devUi';

const fileSize = (n: number | null) =>
  n == null ? '' : n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
const fileKind = (name: string, type: string | null) => (name.includes('.') ? name.split('.').pop()!.toUpperCase() : (type ?? 'FILE').toUpperCase());

const stamp = (iso: string) => {
  const d = new Date(iso);
  const now = new Date();
  const time = d.toLocaleTimeString(document.documentElement.lang === 'de' ? 'de-DE' : 'en-GB', { hour: '2-digit', minute: '2-digit' });
  return d.toDateString() === now.toDateString() ? `Today, ${time}` : `${d.toLocaleDateString(document.documentElement.lang === 'de' ? 'de-DE' : 'en-GB', { day: '2-digit', month: 'short' })}, ${time}`;
};
const show = (v: unknown) => (v == null || v === '' ? '—' : Array.isArray(v) ? v.join(', ') || '—' : String(v));

const TOOLBAR = ['Text ▾', 'B', 'I', 'H₂', '• List', '1. List', '🔗', '</>', '@'];

function Row({ label, children }: { label: string; children: ReactNode }) {
  const { t } = usePrefs();
  return (
    <div className="dv-prop">
      <label>{t(label)}</label>
      <div>{children}</div>
    </div>
  );
}

/** Task Details (borek-flow-screens): description, attachments and activity on the left; Properties and Related tasks on the right. */
export function DevTaskPage() {
  const { t } = usePrefs();
  const { taskId = '' } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const toast = useToast();
  const { data: task, isPending, isError, refetch } = useTask(taskId);
  const statuses = useProjectStatuses(task?.project_id);
  const update = useUpdateTask(task);
  const attachments = useAttachments(taskId);
  const files = useAttachmentActions(taskId);
  const comments = useComments(taskId);
  const activity = useActivity(taskId);
  const addComment = useAddComment(taskId);
  const editComment = useEditComment(taskId);
  const members = useProjectMembers(task?.project_id).data ?? [];
  const sprints = useQuery({
    queryKey: ['projects', 'sprints', task?.project_id],
    queryFn: () => api<{ items: { id: string; name: string; state: string }[] }>(`/projects/${task?.project_id}/sprints`),
    enabled: !!task,
    retry: false,
  });
  const [tab, setTab] = useState<'all' | 'comments' | 'history'>('all');
  const [comment, setComment] = useState('');
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [fileError, setFileError] = useState('');
  const [dropping, setDropping] = useState(false);
  const [blocking, setBlocking] = useState<{ statusId: string; reason: string } | null>(null);
  const [drawer, setDrawer] = useState(false);
  // No relations endpoint yet: kept in page state until the backend adds one.
  const [related, setRelated] = useState<{ relation: Relationship; task: Task }[]>([]);
  const picker = useRef<HTMLInputElement>(null);

  if (isPending) return <section className="dv-task"><LoadingState title="Loading task" /></section>;
  if (isError || !task) return <section className="dv-task"><ErrorState title="We couldn’t load this task" text="It may not exist, or you may not have access." onRetry={() => void refetch()} /></section>;

  // Mirrors the backend: a developer changes the status and priority of their own tasks, and the dates of tasks they made for themselves.
  const mine = task.assignee?.id === user?.id;
  const canSchedule = mine && task.reporter.id === user?.id;
  const fail = (e: unknown) => toast.error(describeApiError(e, t('Could not save your change.')));
  const patch = (p: TaskPatch, done?: () => void) => update.mutate(p, { onSuccess: done, onError: fail });
  const options = statuses.data ?? [task.status];
  const goBack = () => (window.history.state?.idx > 0 ? navigate(-1) : navigate(paths.projectBoard(task.project_id)));
  const conflict = update.error instanceof ApiError && update.error.status === 409;
  const activeSprint = sprints.data?.items.find((s) => s.state === 'active');

  const entries = [
    ...(tab === 'history' ? [] : (comments.data ?? []).map((c) => ({ kind: 'comment' as const, c, at: c.created_at }))),
    ...(tab === 'comments' ? [] : (activity.data?.items ?? []).map((a) => ({ kind: 'audit' as const, a, at: a.created_at }))),
  ].sort((x, y) => (x.at < y.at ? 1 : -1));

  const upload = (picked: File[]) => {
    if (!picked.length) return;
    setFileError('');
    files.upload.mutate(picked, {
      onError: (err) => setFileError(err instanceof ApiError && err.status === 413 ? t('That file is too large (25 MB max).') : describeApiError(err, t('Could not upload the file.'))),
    });
  };

  const priorityOptions = PRIORITIES.map((p) => ({ value: p as TaskPriority, text: t(PRIORITY_LABEL[p]), label: <>{t(PRIORITY_LABEL[p])}</> }));

  return (
    <section className="dv-task">
      <div className="dv-task-top">
        <button type="button" className="dv-back" onClick={goBack}>← <span>{t('Back')}</span></button>
        <span className="dv-key">{task.key}</span>
        <span className="dv-kind">{t('Project task')}</span>
      </div>
      <h2 className="dv-task-title">{task.title}</h2>
      {update.isError && (
        <p className="dv-error" role="alert">{conflict ? t('Someone else changed this task. The latest version has been loaded; try again.') : describeApiError(update.error, t('Could not save your change.'))}</p>
      )}

      <div className="dv-task-grid">
        <section className="dv-pane">
          <h3>{t('Description')}</h3>
          <div className="dv-editor">
            <div className="dv-toolbar" role="toolbar" aria-label={t('Formatting')}>
              {TOOLBAR.map((b) => <button key={b} type="button" disabled tabIndex={-1}>{b}</button>)}
            </div>
            {task.description ? (
              task.description.split(/\n{2,}/).map((block, i) =>
                /^#{1,3} /.test(block) ? <h4 key={i}>{block.replace(/^#{1,3} /, '')}</h4> : <p key={i}>{block}</p>,
              )
            ) : (
              <p>{t('No description added.')}</p>
            )}
          </div>
          <hr />

          <h3>{t('Attachments')}</h3>
          <input
            ref={picker}
            type="file"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.ppt,.pptx,.txt,.md,.rtf,.odt,.ods,.png,.jpg,.jpeg,.gif,.webp,.mp3,.m4a,.wav,.ogg,.opus,.aac,.weba"
            multiple
            hidden
            onChange={(e) => {
              const picked = Array.from(e.target.files ?? []);
              e.target.value = '';
              upload(picked);
            }}
          />
          <button
            type="button"
            className={dropping ? 'dv-drop on' : 'dv-drop'}
            disabled={files.upload.isPending}
            onClick={() => picker.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDropping(true); }}
            onDragLeave={() => setDropping(false)}
            onDrop={(e) => { e.preventDefault(); setDropping(false); upload(Array.from(e.dataTransfer.files)); }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 14V4M4.5 8.5 9 4l4.5 4.5M3 15h12" /></svg>
            {files.upload.isPending ? t('Uploading…') : <>{t('Drop files here, or')} <b>{t('browse files')}</b></>}
          </button>
          {fileError && <p className="dv-error" role="alert">{fileError}</p>}
          {(attachments.data ?? []).length === 0 && !files.upload.isPending && <p className="dv-none">{t('No files attached to this task.')}</p>}
          <ul className="dv-files">
            {(attachments.data ?? []).map((a) => (
              <li key={a.id}>
                {a.kind === 'link' ? (
                  <a href={a.url ?? '#'} target="_blank" rel="noreferrer noopener">{a.name}</a>
                ) : (
                  <button type="button" onClick={() => downloadAttachment(a).catch(() => setFileError(t('Could not download the file.')))}>{a.name}</button>
                )}
                <span>{a.kind === 'link' ? t('Link') : `${fileKind(a.name, a.content_type)} · ${fileSize(a.size_bytes)}`}</span>
                {/* The backend only lets the uploader delete an attachment. */}
                {a.uploaded_by.id === user?.id && (
                  <button type="button" className="rm" aria-label={t('Remove {name}', { name: a.name })} disabled={files.remove.isPending} onClick={() => files.remove.mutate(a.id, { onError: (e) => setFileError(describeApiError(e, t('Could not remove the file.'))) })}>×</button>
                )}
              </li>
            ))}
          </ul>
          <hr />

          <div className="dv-act-head">
            <h3>{t('Activity')}</h3>
            <div className="dv-seg" role="tablist" aria-label={t('Activity')}>
              {(['all', 'comments', 'history'] as const).map((k) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'on' : undefined} onClick={() => setTab(k)}>
                  {t(k === 'all' ? 'All' : k === 'comments' ? 'Comments' : 'Logs')}
                </button>
              ))}
            </div>
          </div>
          {tab !== 'history' && (
            <form
              className="dv-comment"
              onSubmit={(e) => {
                e.preventDefault();
                const body = comment.trim();
                if (!body) return;
                addComment.mutate({ body, mention_ids: mentionIdsFor(body, members) }, { onSuccess: () => setComment(''), onError: () => toast.error(t('Could not post your comment.')) });
              }}
            >
              <MentionInput projectId={task.project_id} label={t('Comment')} placeholder={t('Type a comment...')} value={comment} onChange={setComment} />
              <button type="button" className="at" aria-label={t('Mention someone')} onClick={() => setComment((c) => c + '@')}>@</button>
              <button type="submit" className={comment.trim() ? 'send on' : 'send'} aria-label={t('Send')} disabled={!comment.trim() || addComment.isPending}>↑</button>
            </form>
          )}
          {entries.length ? (
            <ul className="dv-feed">
              {entries.map((e) =>
                e.kind === 'comment' ? (
                  <li key={`c-${e.c.id}`}>
                    <p className="who"><b>{e.c.author.name}</b> · <span>{stamp(e.c.created_at)}</span></p>
                    {editing?.id === e.c.id ? (
                      <form
                        className="dv-edit"
                        onSubmit={(ev) => {
                          ev.preventDefault();
                          const body = editing.text.trim();
                          if (!body) return;
                          editComment.mutate({ id: editing.id, body, mention_ids: mentionIdsFor(body, members) }, { onSuccess: () => setEditing(null), onError: () => toast.error(t('Could not save your comment.')) });
                        }}
                      >
                        <MentionInput projectId={task.project_id} label={t('Edit comment')} value={editing.text} onChange={(text) => setEditing({ id: editing.id, text })} autoFocus />
                        <button type="submit" className="dv-btn on" disabled={!editing.text.trim() || editComment.isPending}>{t('Save')}</button>
                        <button type="button" className="dv-btn" onClick={() => setEditing(null)}>{t('Cancel')}</button>
                      </form>
                    ) : (
                      <>
                        <p>{e.c.body}</p>
                        {/* Only the author can edit a comment. */}
                        {e.c.author.id === user?.id && <button type="button" className="dv-link" onClick={() => setEditing({ id: e.c.id, text: e.c.body })}>{t('Edit')}</button>}
                      </>
                    )}
                  </li>
                ) : (
                  <li key={`a-${e.a.id}`}>
                    <p className="who"><b>{e.a.actor.name}</b> · <span>{stamp(e.a.created_at)}</span></p>
                    <p>{t(e.a.action.replace(/_/g, ' '))}</p>
                    {Object.entries(e.a.changes).map(([field, [from, to]]) => (
                      <p key={field} className="muted">{t(field.replace(/_/g, ' '))}: {show(from)} → {show(to)}</p>
                    ))}
                  </li>
                ),
              )}
            </ul>
          ) : tab !== 'comments' && activity.isError ? (
            <p className="dv-none">{t('Audit log could not be loaded.')}</p>
          ) : (
            !comments.isPending && !activity.isPending && <p className="dv-none">{t('Comments and task updates will appear here.')}</p>
          )}
        </section>

        <aside>
          <section className="dv-pane dv-props">
            <h3>{t('Properties')}</h3>
            <div className="dv-group">
              <h5>{t('ASSIGNMENT')}</h5>
              <Row label="Assignee"><span>{task.assignee?.name || t('Unassigned')}</span></Row>
              <Row label="Reporter"><span>{task.reporter.name || '—'}</span></Row>
            </div>
            <div className="dv-group">
              <h5>{t('TASK INFORMATION')}</h5>
              <Row label="Status">
                {mine ? (
                  <Dropdown
                    value={blocking?.statusId ?? task.status.id}
                    label={t('Status')}
                    color={statusTone(task.status.name, task.status.category)}
                    options={options.map((o) => ({ value: o.id, text: t(o.name), label: <span style={{ color: statusTone(o.name, o.category) }}>{t(o.name)}</span> }))}
                    onChange={(id) => {
                      // A blocked status first needs the reason the backend requires.
                      if (options.find((o) => o.id === id)?.category === 'blocked') return setBlocking({ statusId: id, reason: task.blocked_reason ?? '' });
                      setBlocking(null);
                      patch({ status_id: id });
                    }}
                  />
                ) : (
                  <span style={{ color: statusTone(task.status.name, task.status.category) }}>{t(task.status.name)}</span>
                )}
              </Row>
              {blocking && (
                <Row label="Blocked reason">
                  <form
                    className="dv-reason"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (blocking.reason.trim()) patch({ status_id: blocking.statusId, blocked_reason: blocking.reason.trim() }, () => setBlocking(null));
                    }}
                  >
                    <input autoFocus aria-label={t('Blocked reason')} placeholder={t('Why is this blocked?')} value={blocking.reason} onChange={(e) => setBlocking({ ...blocking, reason: e.target.value })} />
                    <button type="submit" className="dv-btn on" disabled={!blocking.reason.trim() || update.isPending}>{t('Save')}</button>
                    <button type="button" className="dv-btn" onClick={() => setBlocking(null)}>{t('Cancel')}</button>
                  </form>
                </Row>
              )}
              {!blocking && task.status.category === 'blocked' && task.blocked_reason && <Row label="Blocked reason"><span>{task.blocked_reason}</span></Row>}
              <Row label="Priority">
                {mine ? (
                  <Dropdown value={task.priority} label={t('Priority')} options={priorityOptions} onChange={(priority) => patch({ priority })} />
                ) : (
                  <span>{t(PRIORITY_LABEL[task.priority])}</span>
                )}
              </Row>
              <Row label="Task type"><span>{t('Task')}</span></Row>
              <Row label="Labels">
                {task.labels.length ? <ul className="dv-labels">{task.labels.map((l) => <li key={l}>{l}</li>)}</ul> : <span>—</span>}
              </Row>
              <Row label="Estimate">
                {task.estimate_value != null ? (
                  <span className="dv-est"><i>{task.estimate_value}</i><i>{t(task.estimate_unit ?? 'hours')}</i></span>
                ) : (
                  <span>—</span>
                )}
              </Row>
            </div>
            <div className="dv-group">
              <h5>{t('SCHEDULE')}</h5>
              <Row label="Start date">
                {canSchedule ? (
                  <DatePicker label="Start date" value={task.start_date} max={task.due_date} hint="Start date must be on or before due date." error="Pick a date on or before the due date." onChange={(start_date) => patch({ start_date })} />
                ) : (
                  <span>{fmtDate(task.start_date)}</span>
                )}
              </Row>
              <Row label="Due date">
                {canSchedule ? (
                  <DatePicker label="Due date" value={task.due_date} min={task.start_date} hint="Due date must be on or after start date." error="Pick a date on or after the start date." onChange={(due_date) => patch({ due_date })} />
                ) : (
                  <span>{fmtDate(task.due_date)}</span>
                )}
              </Row>
            </div>
            <div className="dv-group">
              <h5>{t('ADDITIONAL')}</h5>
              <Row label="Sprint"><span>{activeSprint && task.status.category !== 'backlog' ? `${activeSprint.name} · ${t('Active')}` : '—'}</span></Row>
              <Row label="Milestone"><span>{t('None linked')}</span></Row>
            </div>
          </section>

          <section className="dv-pane dv-related">
            <div className="dv-rel-head">
              <h3>{t('Related tasks')}</h3>
              <button type="button" className="dv-link" onClick={() => setDrawer(true)}>{t('Relate task')}</button>
            </div>
            {related.length === 0 && <p className="dv-none">{t('No related tasks yet.')}</p>}
            {related.map((r) => (
              <div key={`${r.relation}-${r.task.id}`} className="dv-rel">
                <Link to={paths.task(r.task.id)}>{r.task.key} · {r.task.title}</Link>
                <span title={t(relationLabels[r.relation])}>{t(r.task.status.name)}</span>
              </div>
            ))}
          </section>
        </aside>
      </div>
      {drawer && (
        <RelatedTaskDrawer
          task={task}
          onClose={() => setDrawer(false)}
          onAdd={(relation, other) => {
            setRelated((prev) => (prev.some((r) => r.task.id === other.id && r.relation === relation) ? prev : [...prev, { relation, task: other }]));
            setDrawer(false);
          }}
        />
      )}
    </section>
  );
}
