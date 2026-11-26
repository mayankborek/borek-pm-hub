import { useState, type FormEvent } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { describeApiError } from '@/shared/api/client';
import { usePermissions } from '@/features/admin/permissionsStore';
import { useProjectContext } from './ClientProjectLayout';
import { Badge, EmptyCard, ErrorCard, LoadingCard } from './ui';
import { longDate, paddedDate } from './format';
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
const NOTE: Record<CrStatus, string> = {
  pending: 'Waiting for the project team to pick this up',
  in_review: 'Being reviewed by the project team',
  approved: 'Accepted by the project team',
  declined: 'Declined by the project team',
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
  const [sent, setSent] = useState<Sent | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const access = usePermissions('client')['change-requests'];

  if (access === 'denied') return <EmptyCard title="Change requests are not available" text="Your access to change requests has been turned off." />;
  if (real.missing) {
    return <EmptyCard title="Change requests are not available" text="This project is not connected to the portal service yet." />;
  }
  if (real.isError || list.isError) return <ErrorCard onRetry={() => (real.isError ? window.location.reload() : void list.refetch())} />;
  if (!list.data || !real.id) return <LoadingCard />;

  const { items, counts } = list.data;
  const opened = openId ? items.find((i) => i.id === openId) : undefined;
  if (opened) return <RequestPage canReply={access === 'edit'} cr={opened} projectId={real.id} onBack={() => setOpenId(null)} />;
  const q = query.trim().toLowerCase();
  const shown = items
    .filter((i) => filter === 'all' || i.status === filter)
    .filter((i) => !q || i.code.toLowerCase().includes(q) || i.title.toLowerCase().includes(q));

  return (
    <section className="cr" aria-label={t('Change Requests')}>
      <div className="cr-head">
        <div>
          <h2>{t('Change Requests')}</h2>
          <p>{t('Ask for a change to scope or dates, and follow the answer from your project team.')}</p>
        </div>
        <div className="cr-head-act">
          <span className="cr-count">{counts.total ?? items.length}</span>
          {!composing && access === 'edit' && (
            <button type="button" className="cr-btn" onClick={() => { setSent(null); setComposing(true); }}>{t('New change request')}</button>
          )}
        </div>
      </div>

      {sent && !composing && (
        <div className="cp-card cr-sent" role="status">
          <b>{t('{code} has been received', { code: sent.code })}</b>
          <p>{t('Your project team has been notified and will review it. You can follow the answer here, and we will message you if we need more detail.')}</p>
          {!!sent.failed.length && (
            <p className="cr-error">{t('These files could not be uploaded: {files}', { files: sent.failed.join(', ') })}</p>
          )}
          <div className="cr-actions">
            <button type="button" className="cr-btn" onClick={() => { setFilter('all'); setOpenId(sent.id); setSent(null); }}>{t('View request')}</button>
            <button type="button" className="cr-ghost" onClick={() => setSent(null)}>{t('Dismiss')}</button>
          </div>
        </div>
      )}

      {composing && access === 'edit' && (
        <NewRequest
          projectId={real.id}
          onDone={(result) => {
            setComposing(false);
            if (result) setSent(result);
          }}
        />
      )}

      <div className="cr-stats">
        {([
          ['Total requests', counts.total ?? items.length, 'Across this project'],
          ['In review', counts.in_review ?? 0, 'Awaiting a decision'],
          ['Approved', counts.approved ?? 0, 'Approved requests'],
          ['Declined', counts.declined ?? 0, 'Declined requests'],
        ] as const).map(([label, n, sub]) => (
          <div className="cr-stat" key={label}>
            <div className="cr-l">{t(label)}</div>
            <div className="cr-n">{n}</div>
            <div className="cr-s">{t(sub)}</div>
          </div>
        ))}
      </div>

      <div className="cr-bar">
      <div className="cr-tools">
        <label className="cr-search">
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('Search requests …')} aria-label={t('Search requests')} />
        </label>
        <button type="button" className="cr-ghost" aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}>{t('Filter')}</button>
      </div>

      <div className={showFilters ? 'cr-filters cr-open' : 'cr-filters'} role="tablist" aria-label={t('Filter by status')}>
        {FILTERS.map((f) => (
          <button key={f} type="button" role="tab" aria-selected={filter === f} className={filter === f ? 'cr-on' : undefined} onClick={() => setFilter(f)}>
            {t(f === 'all' ? 'All' : STATUS[f].label)} <span>{f === 'all' ? (counts.total ?? items.length) : (counts[f] ?? 0)}</span>
          </button>
        ))}
      </div>
      </div>

      {shown.length === 0 ? (
        <EmptyCard
          title={items.length === 0 ? 'No change requests yet' : 'Nothing with this status'}
          text={items.length === 0 ? 'Use “New change request” to ask for a change.' : 'Choose another status to see more.'}
        />
      ) : (
        <ul className="cr-list">
          {shown.map((cr) => <RequestCard key={cr.id} cr={cr} onOpen={() => setOpenId(cr.id)} />)}
        </ul>
      )}
      <p className="cr-foot">{t('Only requests explicitly shared with your organisation are shown.')}</p>
    </section>
  );
}

interface Sent {
  id: string;
  code: string;
  failed: string[];
}

function NewRequest({ projectId, onDone }: { projectId: string; onDone: (sent?: Sent) => void }) {
  const { t } = usePrefs();
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
          onDone({ id: created.id, code: created.code, failed });
        },
        onError: (err) => setError(describeApiError(err, t('Your request could not be sent.'))),
      },
    );
  };

  return (
    <div className="cr-modal" role="dialog" aria-modal="true" aria-labelledby="cr-new-title" onKeyDown={(e) => e.key === 'Escape' && !submit.isPending && onDone()}>
    <form className="cp-card cr-form" onSubmit={onSubmit} noValidate>
      <div className="cr-form-head">
        <h3 id="cr-new-title">{t('New change request')}</h3>
        <button type="button" className="cr-x" aria-label={t('Close')} onClick={() => onDone()} disabled={submit.isPending}>×</button>
      </div>
      <p className="cr-form-sub">{t("Tell us what you'd like to change.")}</p>
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
        <button type="button" className="cr-ghost" onClick={() => onDone()} disabled={submit.isPending}>{t('Cancel')}</button>
      </div>
    </form>
    </div>
  );
}


function RequestCard({ cr, onOpen }: { cr: CrItem; onOpen: () => void }) {
  const { t, lang } = usePrefs();
  const s = STATUS[cr.status];
  return (
    <li className="cp-card cr-card">
      <button type="button" className="cr-summary" onClick={onOpen}>
        <span className="cr-ico cr-dt" aria-hidden="true">⇄</span>
        <span className="cr-ttl cr-dt">
          <b>{cr.title}</b>
          <small>{cr.code} · {t('Submitted {date}', { date: paddedDate(lang, isoDay(cr.submitted_at)) })}</small>
        </span>
        <span className="cr-code">{cr.code}</span>
        <b>{cr.title}</b>
        <Badge tone={s.tone}>{t(s.label)}</Badge>
        <small>{longDate(lang, isoDay(cr.submitted_at))}</small>
        <span className="cr-tab">
          <span>{t('Submitted on {date}', { date: paddedDate(lang, isoDay(cr.submitted_at)) })}</span>
          <span>{t('Decision: {status}', { status: t(cr.status === 'approved' ? 'Approved' : cr.status === 'declined' ? 'Declined' : 'Pending') })}</span>
          <small>{t('Updated {date}', { date: paddedDate(lang, isoDay(cr.decided_at ?? cr.review_started_at ?? cr.submitted_at)) })}</small>
          <span className="cr-view">{t('View impact assessment')}</span>
        </span>
        <span className="cr-open-btn">{t('View request')} →</span>
        <span className="cr-foot-line cr-dt">{t(NOTE[cr.status])}</span>
      </button>
    </li>
  );
}

const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();

type Step = { label: string; at: string | null; state: 'done' | 'current' | 'todo'; note?: string };

/** One request: description, files and conversation beside its timeline and impact. */
function RequestPage({ cr, projectId, canReply, onBack }: { cr: CrItem; projectId: string; canReply: boolean; onBack: () => void }) {
  const { t, lang } = usePrefs();
  const toast = useToast();
  const files = useAttachments(projectId, cr.id);
  const comments = useComments(projectId, cr.id);
  const add = useAddComment(projectId, cr.id);
  const [reply, setReply] = useState('');
  const open = cr.status === 'pending' || cr.status === 'in_review';

  const send = (e: FormEvent) => {
    e.preventDefault();
    if (!reply.trim()) return;
    add.mutate(reply.trim(), {
      onSuccess: () => setReply(''),
      onError: (err) => toast.error(describeApiError(err, t('Your message could not be sent.'))),
    });
  };

  const steps: Step[] = [
    { label: 'Submitted', at: cr.submitted_at, state: 'done' },
    {
      label: 'In review',
      at: cr.review_started_at,
      state: cr.status === 'in_review' ? 'current' : cr.review_started_at || !open ? 'done' : 'todo',
      note: cr.status === 'in_review' ? 'The project team is reviewing your request.' : undefined,
    },
    open
      ? { label: 'Decision', at: null, state: 'todo', note: 'Awaiting the review outcome' }
      : { label: cr.status === 'declined' ? 'Declined' : 'Accepted', at: cr.decided_at, state: 'done' },
  ];

  return (
    <section className="cr cr-page" aria-label={cr.title}>
      <button type="button" className="cr-back" onClick={onBack}>← {t('All requests')}</button>
      <h2 className="cr-title">{cr.title}</h2>

      <div className="cr-grid">
        <div className="cr-main">
          <div className="cp-card cr-box">
            <h3 className="cr-h-blue">{t('Description')}</h3>
            <p className="cr-desc">{cr.description}</p>
            {cr.reason && <p className="cr-reason"><b>{t('Reason')}</b> {cr.reason}</p>}
            <p className="cr-meta">{t('Submitted on {date}', { date: paddedDate(lang, isoDay(cr.submitted_at)) })} · {cr.submitted_by}</p>
            <div className="cr-attach">
              <b>{t('Attachments')}</b>
              {files.data?.length ? (
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
              ) : (
                <span>{t('No files attached')}</span>
              )}
            </div>
          </div>

          <div className="cp-card cr-box">
            <h3>{t('Comments')}</h3>
            {comments.isError && <p className="cr-error" role="alert">{t('The conversation could not be loaded.')}</p>}
            <ul className="cr-thread">
              {comments.data?.map((c) => (
                <li key={c.id}>
                  <span className="cr-av" aria-hidden="true">{initials(c.author)}</span>
                  <div>
                    <b>{c.author}{!c.from_client && ` · ${t('Borek team')}`}</b>
                    <small> · {longDate(lang, isoDay(c.created_at))}, {c.created_at.slice(11, 16)}</small>
                    <p>{c.body}</p>
                  </div>
                </li>
              ))}
              {comments.data?.length === 0 && <li className="cr-none">{t('No messages yet.')}</li>}
            </ul>
            {canReply && (
              <form className="cr-reply" onSubmit={send}>
                <h4>{t('Add a comment')}</h4>
                <div className="cr-compose">
                  <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={3} placeholder={t('Write a comment…')} aria-label={t('Message')} />
                  <button type="submit" className="cr-send" disabled={add.isPending || !reply.trim()} aria-label={t('Send')}>↑</button>
                </div>
                <small>{t('Visible to your project team.')}</small>
              </form>
            )}
          </div>
        </div>

        <aside className="cr-side">
          <div className="cp-card cr-box">
            <h3>{t('Request timeline')}</h3>
            <ol className="cr-line">
              {steps.map((st) => (
                <li key={st.label} className={`cr-${st.state}`}>
                  <i aria-hidden="true">{st.state === 'done' ? '✓' : ''}</i>
                  <b>{t(st.label)}</b>
                  {st.at && <small>{longDate(lang, isoDay(st.at))}</small>}
                  {st.state === 'current' && <em>{t('Current status')}</em>}
                  {st.note && <small>{t(st.note)}</small>}
                </li>
              ))}
            </ol>
          </div>

          <div className="cp-card cr-box">
            <h3 className="cr-h-blue">{t('Request details')}</h3>
            <hr />
            {cr.impact_schedule_value !== null ? (
              <>
                <div className="cr-k">{t('Schedule impact')}</div>
                <div className="cr-big">{`${cr.impact_schedule_value > 0 ? '+' : ''}${t(`{n} ${cr.impact_schedule_unit ?? 'days'}`, { n: cr.impact_schedule_value })}${open ? ` ${t('proposed')}` : ''}`}</div>
                {open && <p>{t('Delivery dates stay unchanged until approval.')}</p>}
              </>
            ) : (
              <p>{t('Schedule impact has not been assessed yet.')}</p>
            )}
            {cr.impact_scope && <><div className="cr-k">{t(open ? 'Proposed scope impact' : 'Scope impact')}</div><p>{cr.impact_scope}</p></>}
            {cr.decision_note && <><div className="cr-k">{t('Decision note')}</div><p>{cr.decision_note}</p></>}
            {cr.milestone && (
              <div className="cr-row2">
                <span>{t('Milestone')}</span>
                <span>{cr.milestone.code} · {cr.milestone.name}{cr.requested_date && ` → ${longDate(lang, cr.requested_date)}`}</span>
              </div>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}
