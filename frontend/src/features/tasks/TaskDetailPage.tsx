import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
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
  useDeleteTask,
  useEditComment,
  useProjectMembers,
  useProjectMilestoneOptions,
  useProjectSprints,
  useAttachments,
  useProjectStatuses,
  useTask,
  useUpdateTask,
  ESTIMATE_UNITS,
  type EstimateUnit,
  type TaskPatch,
} from './tasksApi';
import { formatDate } from '@/features/projects/projectUi';
import { RelatedTaskDrawer } from './RelatedTaskDrawer';
import { LINK_KIND, LINK_LABEL, useAddTaskLink, useRemoveTaskLink, useTaskLinks } from './taskLinksApi';
import { AssigneeSelect } from './AssigneeSelect';
import { Avatar } from './TaskParts';
import { DatePicker } from './DatePicker';
import { PriorityIndicator, PrioritySelect } from './PrioritySelect';
import { StatusSelect } from './StatusSelect';
import { LabelChips, LabelPicker } from './LabelPicker';
import { MentionInput, mentionIdsFor } from './MentionInput';
import './taskDetail.css';

const fileSize = (n: number | null) =>
  n == null ? '' : n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;

const stamp = (iso: string) =>
  new Date(iso).toLocaleString(document.documentElement.lang === 'de' ? 'de-DE' : 'en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

const show = (v: unknown) => (v == null || v === '' ? '—' : Array.isArray(v) ? v.join(', ') || '—' : String(v));

const changeText = (field: string, [from, to]: [unknown, unknown], t: (s: string) => string) =>
  `${t(field.replace(/_/g, ' '))}: ${show(from)} → ${show(to)}`;

function Row({ label, children }: { label: string; children: ReactNode }) {
  const { t } = usePrefs();
  return (
    <div className="tdx-row">
      <label>{t(label)}</label>
      {children}
    </div>
  );
}

/** Opens from the Task List (Figma "PM · Related Task · Added"). Edits are staged and sent together by the Save button via PATCH /tasks/{id}. */
export function TaskDetailPage() {
  const { t } = usePrefs();
  const { taskId = '' } = useParams();
  const navigate = useNavigate();
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
  const editComment = useEditComment(taskId);
  const members = useProjectMembers(task?.project_id).data ?? [];
  const sprints = useProjectSprints(task?.project_id).data ?? [];
  const milestones = useProjectMilestoneOptions(task?.project_id).data ?? [];
  const [comment, setComment] = useState('');
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [tab, setTab] = useState<'all' | 'comments' | 'history'>('all');
  const entries = [
    ...(tab === 'history' ? [] : (comments.data ?? []).map((c) => ({ kind: 'comment' as const, c, at: c.created_at }))),
    ...(tab === 'comments' ? [] : (activity.data?.items ?? []).map((a) => ({ kind: 'audit' as const, a, at: a.created_at }))),
  ].sort((x, y) => (x.at < y.at ? 1 : -1));
  const picker = useRef<HTMLInputElement>(null);
  const descRef = useRef<HTMLTextAreaElement>(null);
  const [fileError, setFileError] = useState('');
  // Attachments save as soon as they are picked, but the Save button stays active so the page can be confirmed.
  const [filesChanged, setFilesChanged] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [menu, setMenu] = useState(false);
  const [dropping, setDropping] = useState(false);
  const confirm = useRef<HTMLDialogElement>(null);
  const del = useDeleteTask();
  // The ••• menu closes on any outside click or Escape.
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(false);
    const esc = (e: globalThis.KeyboardEvent) => e.key === 'Escape' && close();
    document.addEventListener('click', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('click', close);
      document.removeEventListener('keydown', esc);
    };
  }, [menu]);
  const links = useTaskLinks(taskId);
  const addLink = useAddTaskLink(taskId);
  const removeLink = useRemoveTaskLink(taskId);
  const related = links.data ?? [];
  // Unsaved edits, sent together by the Save button.
  const [draft, setDraft] = useState<TaskPatch>({});

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
    title: task.title,
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
    sprint_id: task.sprint_id,
    milestone_id: task.milestone_id,
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
      key === 'title' ? draft.title?.trim() : key === 'description' ? draft.description?.trim() || null : key === 'blocked_reason' ? draft.blocked_reason?.trim() || null : draft[key];
    if (JSON.stringify(next) !== JSON.stringify(saved[key])) Object.assign(changes, { [key]: next });
  }
  const dirty = Object.keys(changes).length > 0;
  // A blocked status needs a reason (the backend rejects it otherwise).
  const targetStatus = (statuses.data ?? [task.status]).find((s) => s.id === (draft.status_id ?? task.status.id)) ?? task.status;
  const blocking = targetStatus.category === 'blocked';
  const reason = (draft.blocked_reason !== undefined ? draft.blocked_reason : task.blocked_reason) ?? '';
  const title = draft.title !== undefined ? draft.title : task.title;
  // The backend rejects an empty title.
  const missingTitle = isPm && !title.trim();
  const missingReason = (blocking && !reason.trim()) || missingTitle;
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
        setFilesChanged(false);
      },
      onError: (e) => toast.error(describeApiError(e, t('Could not save your change.'))),
    });
  };
  // Pressing Enter in a single-line field saves, same as the Save button.
  const saveOnEnter = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key !== 'Enter' || e.nativeEvent.isComposing) return;
    e.preventDefault();
    if (!missingReason && !update.isPending) save();
  };
  const view = {
    description: draft.description !== undefined ? (draft.description ?? '') : (task.description ?? ''),
    priority: draft.priority ?? task.priority,
    status_id: draft.status_id ?? task.status.id,
    assignee_id: draft.assignee_id !== undefined ? draft.assignee_id : (task.assignee?.id ?? null),
    start_date: draft.start_date !== undefined ? draft.start_date : task.start_date,
    due_date: draft.due_date !== undefined ? draft.due_date : task.due_date,
    sprint_id: draft.sprint_id !== undefined ? draft.sprint_id : task.sprint_id,
    milestone_id: draft.milestone_id !== undefined ? draft.milestone_id : task.milestone_id,
  };
  // Only planned and active sprints accept tasks; a completed sprint stays selectable only while the task is already in it.
  const sprintOptions = sprints.filter((s) => s.state !== 'completed' || s.id === task.sprint_id);
  const sprintName = sprints.find((s) => s.id === task.sprint_id)?.name;
  const milestone = milestones.find((m) => m.id === task.milestone_id);
  const estimate = {
    value: draft.estimate_value !== undefined ? draft.estimate_value : task.estimate_value,
    unit: draft.estimate_unit !== undefined ? draft.estimate_unit : task.estimate_unit,
  };
  // Toolbar buttons wrap the selected text (or insert the marker) in the description.
  const format = (pre: string, post: string) => {
    const el = descRef.current;
    if (!el || (!pre && !post)) return;
    const { selectionStart: a, selectionEnd: b, value } = el;
    const next = value.slice(0, a) + pre + value.slice(a, b) + post + value.slice(b);
    stage({ description: next });
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(a + pre.length, b + pre.length);
    });
  };
  // Status and priority are the developer's to change only on tasks assigned to them.
  const canStatus = isPm || task.assignee?.id === user?.id;
  const canPriority = canStatus;
  // PMs stage edits for the Save button; developers apply each change straight away, as they do for status.
  const edit = (patch: TaskPatch) =>
    isPm ? stage(patch) : update.mutate(patch, { onError: (e) => toast.error(describeApiError(e, t('Could not save your change.'))) });
  const upload = (picked: File[]) => {
    if (!picked.length) return;
    setFileError('');
    files.upload.mutate(picked, {
      onSuccess: () => setFilesChanged(true),
      onError: (err) =>
        setFileError(err instanceof ApiError && err.status === 413 ? t('That file is too large (25 MB max).') : describeApiError(err, t('Could not upload the file.'))),
    });
  };
  const conflict = update.error instanceof ApiError && update.error.status === 409;
  // Return to wherever the user came from; fall back to the list/board when the page was opened directly.
  const goBack = () => (window.history.state?.idx > 0 ? navigate(-1) : navigate(isPm ? paths.tasks : paths.projectBoard(task.project_id)));

  const fileList = attachments.data ?? [];

  return (
    <section className="page-body task-detail tdx">
      <header className="tdx-header">
      <div className="tdx-top">
        <button type="button" className="tdx-back" onClick={goBack}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M13 7H1.5M7 1.5 1.5 7 7 12.5" /></svg>
          {t('Back')}
        </button>
        <span className="tdx-id">{task.key}</span>
        <span className="tdx-link">{t('Project task')}</span>
        <div className="tdx-right">
          <button type="button" className="tdx-btn primary" disabled={(!dirty && !filesChanged) || missingReason || update.isPending} onClick={save}>
            {t(update.isPending ? 'Saving…' : 'Save')}
          </button>
          {isPm && (
            <div className="td-more">
              <button
                type="button"
                className="tdx-more"
                aria-label={t('Task actions')}
                aria-expanded={menu}
                onClick={(e) => {
                  e.stopPropagation();
                  setMenu((m) => !m);
                }}
              >
                •••
              </button>
              {menu && (
                <div className="tdx-menu" role="menu">
                  <button type="button" role="menuitem" onClick={() => confirm.current?.showModal()}>
                    {t('Delete task')}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {isPm ? (
        <input
          className="tdx-title"
          aria-label={t('Task title')}
          aria-invalid={missingTitle}
          maxLength={200}
          value={title}
          onChange={(e) => stage({ title: e.target.value })}
          onKeyDown={saveOnEnter}
        />
      ) : (
        <h2 className="tdx-title">{task.title}</h2>
      )}
      </header>
      {update.isError && (
        <p className="td-error" role="alert">
          {conflict ? t('Someone else changed this task. The latest version has been loaded; try again.') : describeApiError(update.error, t('Could not save your change.'))}
        </p>
      )}

      <div className="tdx-grid">
        <section className="tdx-card tdx-main">
          <div className="tdx-head">
            <h3>{t('Description')}</h3>
            {isPm && (
              <button type="button" className="tdx-link" onClick={() => descRef.current?.focus()}>
                {t('Edit description')}
              </button>
            )}
          </div>
          <div className="tdx-editor">
            {isPm && (
              <div className="tdx-toolbar" role="toolbar" aria-label={t('Formatting')}>
                {([
                  ['Text ▾', '', '', t('Text')],
                  ['B', '**', '**', t('Bold')],
                  ['I', '_', '_', t('Italic')],
                  ['H2', '## ', '', t('Heading 2')],
                  ['• List', '- ', '', t('Bullet list')],
                  ['1. List', '1. ', '', t('Numbered list')],
                  ['🔗', '[', '](https://)', t('Link')],
                  ['</>', '`', '`', t('Code')],
                  ['@', '@', '', t('Mention')],
                ] as const).map(([label, pre, post, name]) => (
                  <button key={name} type="button" aria-label={name} onMouseDown={(e) => e.preventDefault()} onClick={() => format(pre, post)}>
                    {label}
                  </button>
                ))}
              </div>
            )}
            {isPm ? (
              <textarea
                ref={descRef}
                aria-label={t('Description')}
                placeholder={t('No description added.')}
                value={view.description}
                onChange={(e) => stage({ description: e.target.value })}
                // Enter saves; Shift+Enter adds a new line.
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    if (!missingReason && !update.isPending) save();
                  }
                }}
              />
            ) : (
              <p>{view.description || t('No description added.')}</p>
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
            className={dropping ? 'tdx-drop on' : 'tdx-drop'}
            disabled={files.upload.isPending}
            onClick={() => picker.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDropping(true);
            }}
            onDragLeave={() => setDropping(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDropping(false);
              upload(Array.from(e.dataTransfer.files));
            }}
          >
            <span className="tdx-up" aria-hidden="true">⇧</span>
            {files.upload.isPending ? t('Uploading…') : <>{t('Drop files here, or')} <span className="tdx-link">{t('browse files')}</span></>}
          </button>
          {fileError && (
            <p className="td-error" role="alert">
              {fileError}
            </p>
          )}
          {fileList.length === 0 && !files.upload.isPending && <p className="tdx-none">{t('No files attached to this task.')}</p>}
          {fileList.map((a) => (
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
          <hr />

          <div className="tdx-head">
            <h3 id="td-activity-h">{t('Activity')}</h3>
            <div className="tdx-seg" role="tablist" aria-label={t('Activity')}>
              {(['all', 'comments', 'history'] as const).map((k) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'on' : undefined} onClick={() => setTab(k)}>
                  {t(k === 'all' ? 'All' : k === 'comments' ? 'Comments' : 'Logs')}
                </button>
              ))}
            </div>
          </div>
          {tab !== 'history' && (
            <form
              className="tdx-comment"
              onSubmit={(e) => {
                e.preventDefault();
                const body = comment.trim();
                if (!body) return;
                addComment.mutate(
                  { body, mention_ids: mentionIdsFor(body, members) },
                  {
                    onSuccess: () => setComment(''),
                    onError: () => toast.error(t('Could not post your comment.')),
                  },
                );
              }}
            >
              <MentionInput projectId={task.project_id} label={t('Comment')} placeholder={t('Type a comment...')} value={comment} onChange={setComment} />
              <button type="button" className="tdx-at" aria-label={t('Mention someone')} onClick={() => setComment((c) => c + '@')}>
                @
              </button>
              <button type="submit" className={comment.trim() ? 'tdx-send on' : 'tdx-send'} aria-label={t('Send')} disabled={!comment.trim() || addComment.isPending}>
                ↑
              </button>
            </form>
          )}
          {entries.length ? (
            <ul className="td-comments td-scroll">
              {entries.map((e) =>
                e.kind === 'comment' ? (
                  <li key={`c-${e.c.id}`} className="td-comment">
                    <Avatar user={e.c.author} round />
                    <div>
                      <strong>{e.c.author.name}</strong> <span>{stamp(e.c.created_at)}</span>
                      {editing?.id === e.c.id ? (
                        <form
                          className="td-composer"
                          onSubmit={(ev) => {
                            ev.preventDefault();
                            const body = editing.text.trim();
                            if (!body) return;
                            editComment.mutate(
                              { id: editing.id, body, mention_ids: mentionIdsFor(body, members) },
                              { onSuccess: () => setEditing(null), onError: () => toast.error(t('Could not save your comment.')) },
                            );
                          }}
                        >
                          <MentionInput
                            projectId={task.project_id}
                            label={t('Edit comment')}
                            value={editing.text}
                            onChange={(text) => setEditing({ id: editing.id, text })}
                            autoFocus
                          />
                          <button type="submit" className="tdx-btn primary" disabled={!editing.text.trim() || editComment.isPending}>
                            {t('Save')}
                          </button>
                          <button type="button" className="tdx-btn" onClick={() => setEditing(null)}>
                            {t('Cancel')}
                          </button>
                        </form>
                      ) : (
                        <>
                          <p>{e.c.body}</p>
                          {/* Only the author can edit a comment. */}
                          {e.c.author.id === user?.id && (
                            <button type="button" className="td-link" onClick={() => setEditing({ id: e.c.id, text: e.c.body })}>
                              {t('Edit')}
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </li>
                ) : (
                  <li key={`a-${e.a.id}`} className="td-comment">
                    <Avatar user={e.a.actor} round />
                    <div>
                      <strong>{e.a.actor.name}</strong> <span>{stamp(e.a.created_at)}</span>
                      <p>{t(e.a.action.replace(/_/g, ' '))}</p>
                      {Object.entries(e.a.changes).map(([field, change]) => (
                        <p key={field}>{changeText(field, change, t)}</p>
                      ))}
                    </div>
                  </li>
                ),
              )}
            </ul>
          ) : tab !== 'comments' && activity.isError ? (
            <p className="tdx-sub">{t('Audit log could not be loaded.')}</p>
          ) : (
            !comments.isPending &&
            !activity.isPending && (
              <>
                <h4>{t('Nothing here yet')}</h4>
                <p className="tdx-sub">{t('Comments and task updates will appear here.')}</p>
              </>
            )
          )}
        </section>

        <div>
          <section className="tdx-card tdx-props">
            <h3>{t('Properties')}</h3>
            <div className="tdx-group">
              <h5>{t('ASSIGNMENT')}</h5>
              <Row label="Assignee">
                {isPm ? (
                  <AssigneeSelect projectId={task.project_id} value={view.assignee_id} current={task.assignee} onChange={(assignee_id) => edit({ assignee_id })} />
                ) : (
                  <span className="td-static">{task.assignee?.name || t('Unassigned')}</span>
                )}
              </Row>
              <Row label="Reporter">
                <span className="td-static">{task.reporter.name || '—'}</span>
              </Row>
            </div>
            <div className="tdx-group">
              <h5>{t('TASK INFORMATION')}</h5>
              <Row label="Status">
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
                      onKeyDown={saveOnEnter}
                    />
                  ) : (
                    <span className="td-static">{task.blocked_reason || '—'}</span>
                  )}
                </Row>
              )}
              <Row label="Priority">
                {canPriority ? (
                  <PrioritySelect value={view.priority} onChange={(priority) => edit({ priority })} />
                ) : (
                  <PriorityIndicator priority={view.priority} />
                )}
              </Row>
              <Row label="Task type">
                <span className="td-static">{t('Task')}</span>
              </Row>
              <Row label="Labels">
                {isPm ? (
                  <LabelPicker
                    projectId={task.project_id}
                    value={draft.labels ?? task.labels}
                    onChange={(labels) => stage({ labels })}
                    onSubmit={() => !missingReason && !update.isPending && save()}
                  />
                ) : (
                  <LabelChips labels={task.labels} />
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
                      onKeyDown={saveOnEnter}
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
            </div>
            <div className="tdx-group">
              <h5>{t('SCHEDULE')}</h5>
              <Row label="Start date">
                {canSchedule ? (
                  <DatePicker
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
                {canSchedule ? (
                  <DatePicker
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
            </div>
            <div className="tdx-group">
              <h5>{t('ADDITIONAL')}</h5>
              <Row label="Sprint">
                {isPm ? (
                  <select aria-label={t('Sprint')} value={view.sprint_id ?? ''} onChange={(e) => stage({ sprint_id: e.target.value || null })}>
                    <option value="">{t('Backlog')}</option>
                    {sprintOptions.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                        {s.state === 'completed' ? ` (${t('completed')})` : ''}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="td-static">{task.sprint_id ? (sprintName ?? '…') : t('Backlog')}</span>
                )}
              </Row>
              <Row label="Milestone">
                {isPm ? (
                  <select aria-label={t('Milestone')} value={view.milestone_id ?? ''} onChange={(e) => stage({ milestone_id: e.target.value || null })}>
                    <option value="">{t('None linked')}</option>
                    {milestones.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.code} · {m.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="td-static">{task.milestone_id ? (milestone ? `${milestone.code} · ${milestone.name}` : '…') : t('None linked')}</span>
                )}
              </Row>
            </div>
          </section>

          <section className="tdx-card tdx-related">
            <div className="tdx-head">
              <h3>{t('Related tasks')}</h3>
              <button type="button" className="tdx-link" onClick={() => setDrawer(true)}>
                {t('Relate task')}
              </button>
            </div>
            {links.isError && <p className="td-error" role="alert">{t('Related tasks could not be loaded.')}</p>}
            {!links.isError && !links.isPending && related.length === 0 && <p className="tdx-empty">{t('No related tasks yet.')}</p>}
            {related.map((r) => (
              <div key={r.id} className="td-related">
                <Link to={paths.task(r.task.id)}>
                  {r.task.key} · {r.task.title}
                </Link>
                <span>
                  {t(LINK_LABEL[r.kind] ?? r.label)} · {t(r.task.status.name)}
                </span>
                <button
                  type="button"
                  className="tdx-link"
                  aria-label={t('Remove link to {key}', { key: r.task.key })}
                  disabled={removeLink.isPending}
                  onClick={() => removeLink.mutate(r.id, { onError: (e) => toast.error(describeApiError(e, t('Could not remove the link.'))) })}
                >
                  {t('Remove')}
                </button>
              </div>
            ))}
          </section>
        </div>
      </div>
      <dialog ref={confirm} className="td-dialog" aria-labelledby="td-del-h">
        <h3 id="td-del-h">{t('Delete task?')}</h3>
        <p>
          {t('Delete {key} · {title}?', { key: task.key, title: task.title })}
          <br />
          {t('This action cannot be undone.')}
        </p>
        {del.isError && (
          <p className="td-error" role="alert">
            {describeApiError(del.error, t('Could not delete the task.'))}
          </p>
        )}
        <div className="td-acts">
          <button type="button" className="btn secondary" onClick={() => confirm.current?.close()}>
            {t('Cancel')}
          </button>
          <button
            type="button"
            className="btn td-danger"
            disabled={del.isPending}
            onClick={() => del.mutate(task.id, { onSuccess: () => navigate(isPm ? paths.tasks : paths.projectBoard(task.project_id), { replace: true }) })}
          >
            {t('Delete task')}
          </button>
        </div>
      </dialog>
      {drawer && (
        <RelatedTaskDrawer
          task={task}
          onClose={() => setDrawer(false)}
          onAdd={(relation, other) =>
            addLink.mutate(
              { kind: LINK_KIND[relation], otherId: other.id },
              { onSuccess: () => setDrawer(false), onError: (e) => toast.error(describeApiError(e, t('Could not add the link.'))) },
            )
          }
          busy={addLink.isPending}
        />
      )}
    </section>
  );
}
