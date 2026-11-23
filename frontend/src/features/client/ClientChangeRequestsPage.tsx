import { useState, type FormEvent } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { describeApiError } from '@/shared/api/client';
import { useProjectContext } from './ClientProjectLayout';
import { Badge, EmptyCard, ErrorCard, LoadingCard } from './ui';
import { longDate } from './format';
import type { Tone } from './labels';
import {
  downloadAttachment,
  useAddComment,
  useApiProjectId,
  useAttachments,
  useChangeRequests,
  useComments,
  useShareableMilestones,
  useSubmitChangeRequest,
  type CrItem,
  type CrStatus,
} from './changeRequestsApi';

const STATUS: Record<CrStatus, { label: string; tone: Tone }> = {
  pending: { label: 'Submitted', tone: 'neutral' },
  in_review: { label: 'In review', tone: 'info' },
  approved: { label: 'Accepted', tone: 'success' },
  declined: { label: 'Declined', tone: 'danger' },
};
const FILTERS: (CrStatus | 'all')[] = ['all', 'pending', 'in_review', 'approved', 'declined'];
const MAX_FILES = 5;

const isoDay = (stamp: string) => stamp.slice(0, 10);
const size = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

/** Client Change Requests: raise a request, follow it through review and talk to the team about it. */
export function ClientChangeRequestsPage() {
  const { t } = usePrefs();
  const { project } = useProjectContext();
  const real = useApiProjectId(project);
  const list = useChangeRequests(real.id);
  const [filter, setFilter] = useState<CrStatus | 'all'>('all');
  const [composing, setComposing] = useState(false);

  if (real.missing) {
    return <EmptyCard title="Change requests are not available" text="This project is not connected to the portal service yet." />;
  }
  if (real.isError || list.isError) return <ErrorCard onRetry={() => (real.isError ? window.location.reload() : void list.refetch())} />;
  if (!list.data || !real.id) return <LoadingCard />;

  const { items, counts } = list.data;
  const shown = filter === 'all' ? items : items.filter((i) => i.status === filter);

  return (
    <section className="cr" aria-label={t('Change Requests')}>
      <div className="cr-head">
        <div>
          <h2>{t('Change Requests')}</h2>
          <p>{t('Ask for a change to scope or dates, and follow the answer from your project team.')}</p>
        </div>
        {!composing && (
          <button type="button" className="cr-btn" onClick={() => setComposing(true)}>{t('New change request')}</button>
        )}
      </div>

      {composing && <NewRequest projectId={real.id} onDone={() => setComposing(false)} />}

      <div className="cr-filters" role="tablist" aria-label={t('Filter by status')}>
        {FILTERS.map((f) => (
          <button key={f} type="button" role="tab" aria-selected={filter === f} className={filter === f ? 'cr-on' : undefined} onClick={() => setFilter(f)}>
            {t(f === 'all' ? 'All' : STATUS[f].label)} <span>{f === 'all' ? (counts.total ?? items.length) : (counts[f] ?? 0)}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <EmptyCard
          title={items.length === 0 ? 'No change requests yet' : 'Nothing with this status'}
          text={items.length === 0 ? 'Use “New change request” to ask for a change.' : 'Choose another status to see more.'}
        />
      ) : (
        <ul className="cr-list">
          {shown.map((cr) => <RequestCard key={cr.id} cr={cr} projectId={real.id!} />)}
        </ul>
      )}
    </section>
  );
}

function NewRequest({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const milestones = useShareableMilestones(projectId);
  const submit = useSubmitChangeRequest(projectId);
  const [form, setForm] = useState({ title: '', description: '', reason: '', milestone_id: '', requested_date: '' });
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string>();
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(undefined);
    if (!form.title.trim() || !form.description.trim()) return setError(t('Add a title and a description.'));
    if (form.requested_date && !form.milestone_id) return setError(t('Choose the milestone the new date is for.'));
    const draft = {
      title: form.title.trim(),
      description: form.description.trim(),
      ...(form.reason.trim() && { reason: form.reason.trim() }),
      ...(form.milestone_id && { milestone_id: form.milestone_id }),
      ...(form.requested_date && { requested_date: form.requested_date }),
    };
    submit.mutate(
      { draft, files },
      {
        onSuccess: ({ created, failed }) => {
          if (failed.length) toast.error(t('{code} was sent, but these files could not be uploaded: {files}', { code: created.code, files: failed.join(', ') }));
          else toast.success(t('{code} sent to your project team', { code: created.code }));
          onDone();
        },
        onError: (err) => setError(describeApiError(err, t('Your request could not be sent.'))),
      },
    );
  };

  return (
    <form className="cp-card cr-form" onSubmit={onSubmit} noValidate>
      <h3>{t('New change request')}</h3>
      <label>
        {t('Title')}
        <input value={form.title} onChange={set('title')} maxLength={200} required />
      </label>
      <label>
        {t('What would you like to change?')}
        <textarea value={form.description} onChange={set('description')} rows={4} required />
      </label>
      <label>
        {t('Why is it needed? (optional)')}
        <textarea value={form.reason} onChange={set('reason')} rows={2} />
      </label>
      <div className="cr-row">
        <label>
          {t('Milestone (optional)')}
          <select
            value={form.milestone_id}
            onChange={(e) => setForm((f) => ({ ...f, milestone_id: e.target.value, requested_date: e.target.value ? f.requested_date : '' }))}
          >
            <option value="">{t('None')}</option>
            {milestones.data?.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}
          </select>
        </label>
        <label>
          {t('New date wanted (optional)')}
          <input type="date" value={form.requested_date} onChange={set('requested_date')} disabled={!form.milestone_id} />
        </label>
      </div>
      <label>
        {t('Files (optional)')}
        <input type="file" multiple onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, MAX_FILES))} />
        <small>{t('Up to {n} files.', { n: MAX_FILES })}</small>
      </label>
      {error && <p className="cr-error" role="alert">{error}</p>}
      <div className="cr-actions">
        <button type="submit" className="cr-btn" disabled={submit.isPending}>{submit.isPending ? t('Sending…') : t('Send request')}</button>
        <button type="button" className="cr-ghost" onClick={onDone} disabled={submit.isPending}>{t('Cancel')}</button>
      </div>
    </form>
  );
}

function RequestCard({ cr, projectId }: { cr: CrItem; projectId: string }) {
  const { t, lang } = usePrefs();
  const [open, setOpen] = useState(false);
  const s = STATUS[cr.status];
  return (
    <li className="cp-card cr-card">
      <button type="button" className="cr-summary" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="cr-code">{cr.code}</span>
        <b>{cr.title}</b>
        <Badge tone={s.tone}>{t(s.label)}</Badge>
        <small>{longDate(lang, isoDay(cr.submitted_at))}</small>
      </button>
      {open && <RequestDetail cr={cr} projectId={projectId} />}
    </li>
  );
}

function RequestDetail({ cr, projectId }: { cr: CrItem; projectId: string }) {
  const { t, lang } = usePrefs();
  const toast = useToast();
  const files = useAttachments(projectId, cr.id);
  const comments = useComments(projectId, cr.id);
  const add = useAddComment(projectId, cr.id);
  const [reply, setReply] = useState('');

  const steps: [string, string | null][] = [
    ['Submitted', cr.submitted_at],
    ['In review', cr.review_started_at],
    [cr.status === 'declined' ? 'Declined' : 'Accepted', cr.decided_at],
  ];
  const send = (e: FormEvent) => {
    e.preventDefault();
    if (!reply.trim()) return;
    add.mutate(reply.trim(), {
      onSuccess: () => setReply(''),
      onError: (err) => toast.error(describeApiError(err, t('Your message could not be sent.'))),
    });
  };

  return (
    <div className="cr-detail">
      <ol className="cr-steps" aria-label={t('Progress')}>
        {steps.map(([label, at]) => (
          <li key={label} className={at ? 'cr-done' : undefined}>
            <b>{t(label)}</b>
            <small>{at ? longDate(lang, isoDay(at)) : '—'}</small>
          </li>
        ))}
      </ol>

      <dl>
        <dt>{t('Request')}</dt><dd>{cr.description}</dd>
        {cr.reason && <><dt>{t('Reason')}</dt><dd>{cr.reason}</dd></>}
        {cr.milestone && (
          <>
            <dt>{t('Milestone')}</dt>
            <dd>{cr.milestone.code} · {cr.milestone.name}{cr.requested_date && ` → ${longDate(lang, cr.requested_date)}`}</dd>
          </>
        )}
        <dt>{t('Raised by')}</dt><dd>{cr.submitted_by}</dd>
        {cr.impact_schedule_days !== null && (
          <><dt>{t(cr.status === 'pending' || cr.status === 'in_review' ? 'Proposed schedule impact' : 'Schedule impact')}</dt><dd>{t('{n} days', { n: cr.impact_schedule_days })}</dd></>
        )}
        {cr.impact_scope && <><dt>{t(cr.status === 'pending' || cr.status === 'in_review' ? 'Proposed scope impact' : 'Scope impact')}</dt><dd>{cr.impact_scope}</dd></>}
        {cr.decision_note && <><dt>{t('Decision note')}</dt><dd>{cr.decision_note}</dd></>}
      </dl>

      {!!files.data?.length && (
        <>
          <h4>{t('Files')}</h4>
          <ul className="cr-files">
            {files.data.map((f) => (
              <li key={f.id}>
                <button
                  type="button"
                  onClick={() => downloadAttachment(projectId, cr.id, f).catch((err) => toast.error(describeApiError(err, t('The file could not be downloaded.'))))}
                >
                  {f.name}
                </button>
                <small>{size(f.size_bytes)} · {f.uploaded_by}</small>
              </li>
            ))}
          </ul>
        </>
      )}

      <h4>{t('Conversation')}</h4>
      {comments.isError && <p className="cr-error" role="alert">{t('The conversation could not be loaded.')}</p>}
      <ul className="cr-thread">
        {comments.data?.map((c) => (
          <li key={c.id} className={c.from_client ? 'cr-mine' : undefined}>
            <b>{c.author}{!c.from_client && ` · ${t('Borek team')}`}</b>
            <small>{longDate(lang, isoDay(c.created_at))}</small>
            <p>{c.body}</p>
          </li>
        ))}
        {comments.data?.length === 0 && <li className="cr-none">{t('No messages yet.')}</li>}
      </ul>
      <form className="cr-reply" onSubmit={send}>
        <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={2} placeholder={t('Write a message to your project team')} aria-label={t('Message')} />
        <button type="submit" className="cr-btn" disabled={add.isPending || !reply.trim()}>{t('Send')}</button>
      </form>
    </div>
  );
}
