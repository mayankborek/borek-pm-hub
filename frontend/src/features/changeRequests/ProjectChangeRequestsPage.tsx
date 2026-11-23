import { useState, type FormEvent } from 'react';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Pill, type Tone } from '@/shared/ui/Pill';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { useProjectContext } from '@/features/projects/ProjectLayout';
import { downloadAttachment, type CrStatus } from '@/features/client/changeRequestsApi';
import {
  useDecide,
  useSaveImpact,
  useStaffAddComment,
  useStaffAttachments,
  useStaffChangeRequests,
  useStaffComments,
  useStartReview,
  type StaffCr,
} from './changeRequestsStaffApi';
import '@/features/requirements/requirements.css';
import './changeRequests.css';

// Same wording as the client portal, so both sides name a status the same way.
const STATUS: Record<CrStatus, { label: string; tone: Tone }> = {
  pending: { label: 'Submitted', tone: 'risk' },
  in_review: { label: 'In review', tone: 'progress' },
  approved: { label: 'Accepted', tone: 'track' },
  declined: { label: 'Declined', tone: 'overdue' },
};
const FILTERS: (CrStatus | 'all')[] = ['all', 'pending', 'in_review', 'approved', 'declined'];

const day = (stamp: string) => stamp.slice(0, 10);
const num = (v: string) => (v.trim() === '' ? null : Number(v));

/** Change Requests tab: the queue of requests clients raise, with impact, decision and the shared conversation. */
export function ProjectChangeRequestsPage() {
  const project = useProjectContext();
  const { t } = usePrefs();
  const list = useStaffChangeRequests(project.id);
  const [filter, setFilter] = useState<CrStatus | 'all'>('pending');

  if (list.isError) return <ErrorState title="We couldn’t load the change requests" onRetry={() => void list.refetch()} />;
  if (!list.data) return <LoadingState title="Loading change requests" />;

  const { items, counts } = list.data;
  const shown = filter === 'all' ? items : items.filter((r) => r.status === filter);

  return (
    <section className="req" aria-label={t('Change Requests')}>
      <div className="req-head">
        <p>{t('Requests raised by the client. Add the impact, decide, and talk to the client here.')}</p>
      </div>

      <div className="req-filters" role="tablist" aria-label={t('Filter by status')}>
        {FILTERS.map((f) => (
          <button key={f} type="button" role="tab" aria-selected={filter === f} className={filter === f ? 'req-on' : undefined} onClick={() => setFilter(f)}>
            {t(f === 'all' ? 'All' : STATUS[f].label)} <span>{f === 'all' ? (counts.total ?? items.length) : (counts[f] ?? 0)}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <EmptyState
          title={items.length === 0 ? 'No change requests yet' : 'Nothing with this status'}
          text={items.length === 0 ? 'Requests the client raises in the portal appear here.' : 'Choose another status to see more.'}
        />
      ) : (
        <ul className="req-list">
          {shown.map((cr) => <RequestCard key={cr.id} cr={cr} projectId={project.id} />)}
        </ul>
      )}
    </section>
  );
}

function RequestCard({ cr, projectId }: { cr: StaffCr; projectId: string }) {
  const { t } = usePrefs();
  const [open, setOpen] = useState(false);
  const s = STATUS[cr.status];
  return (
    <li className="req-card">
      <button type="button" className="req-summary" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="req-code">{cr.code}</span>
        <b>{cr.title}</b>
        {cr.status === 'pending' && <span className="crq-new">{t('New')}</span>}
        <span className="crq-flag">{cr.submitted_by.name} · {day(cr.created_at)}</span>
        <Pill tone={s.tone}>{s.label}</Pill>
      </button>
      {open && <RequestDetail cr={cr} projectId={projectId} />}
    </li>
  );
}

function RequestDetail({ cr, projectId }: { cr: StaffCr; projectId: string }) {
  const { t } = usePrefs();
  const toast = useToast();
  const start = useStartReview(projectId, cr);
  const open = cr.status === 'pending' || cr.status === 'in_review';
  const files = useStaffAttachments(projectId, cr.id);

  const onStart = () =>
    start.mutate(undefined, {
      onSuccess: () => toast.success(t('{code} is now in review. The client can see this.', { code: cr.code })),
      onError: (err) => toast.error(describeApiError(err, t('The review could not be started.'))),
    });

  return (
    <div className="req-detail">
      <dl className="crq-dl">
        <dt>{t('Request')}</dt><dd>{cr.description}</dd>
        {cr.reason && <><dt>{t('Reason')}</dt><dd>{cr.reason}</dd></>}
        {cr.milestone && (
          <>
            <dt>{t('Milestone')}</dt>
            <dd>
              {cr.milestone.code} · {cr.milestone.name} ({t('due {date}', { date: cr.milestone.due_date })})
              {cr.requested_date && ` → ${cr.requested_date}`}
            </dd>
          </>
        )}
        <dt>{t('Raised by')}</dt><dd>{cr.submitted_by.name}{cr.submitted_by_client && ` · ${t('Client')}`}</dd>
        {cr.decision_note && <><dt>{t('Decision note')}</dt><dd>{cr.decision_note}</dd></>}
        {cr.decided_by && cr.decided_at && <><dt>{t('Decided')}</dt><dd>{cr.decided_by.name} · {day(cr.decided_at)}</dd></>}
      </dl>

      {!!files.data?.length && (
        <ul className="crq-files">
          {files.data.map((f) => (
            <li key={f.id}>
              <button
                type="button"
                onClick={() => downloadAttachment(projectId, cr.id, f).catch((err) => toast.error(describeApiError(err, t('The file could not be downloaded.'))))}
              >
                {f.name}
              </button>
              <small>{f.uploaded_by}</small>
            </li>
          ))}
        </ul>
      )}

      {cr.status === 'pending' && (
        <div className="req-actions">
          <button type="button" className="btn" onClick={onStart} disabled={start.isPending}>
            {start.isPending ? t('Starting…') : t('Start review')}
          </button>
        </div>
      )}

      {open ? <ImpactForm cr={cr} projectId={projectId} /> : <ImpactSummary cr={cr} />}
      {cr.status === 'in_review' && <DecisionForm cr={cr} projectId={projectId} />}
      <Conversation cr={cr} projectId={projectId} />
    </div>
  );
}

function ImpactSummary({ cr }: { cr: StaffCr }) {
  const { t } = usePrefs();
  if (cr.impact_schedule_days === null && cr.impact_effort_hours === null && !cr.impact_scope) return null;
  return (
    <dl className="crq-dl">
      {cr.impact_schedule_days !== null && <><dt>{t('Schedule impact')}</dt><dd>{t('{n} days', { n: cr.impact_schedule_days })}</dd></>}
      {cr.impact_effort_hours !== null && <><dt>{t('Effort')}</dt><dd>{t('{n} hours', { n: cr.impact_effort_hours })}</dd></>}
      {cr.impact_scope && <><dt>{t('Scope impact')}</dt><dd>{cr.impact_scope}</dd></>}
    </dl>
  );
}

/** Schedule days and scope are shared with the client as soon as they are saved (the proposed impact); effort hours stay internal. */
function ImpactForm({ cr, projectId }: { cr: StaffCr; projectId: string }) {
  const { t } = usePrefs();
  const toast = useToast();
  const save = useSaveImpact(projectId, cr);
  const [days, setDays] = useState(cr.impact_schedule_days?.toString() ?? '');
  const [hours, setHours] = useState(cr.impact_effort_hours?.toString() ?? '');
  const [scope, setScope] = useState(cr.impact_scope ?? '');

  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(
      { impact_schedule_days: num(days), impact_effort_hours: num(hours), impact_scope: scope.trim() || null },
      {
        onSuccess: () => toast.success(t('Impact saved')),
        onError: (err) => toast.error(describeApiError(err, t('The impact could not be saved.'))),
      },
    );
  };

  return (
    <form className="crq-impact" onSubmit={submit}>
      <b>{t('Proposed impact')}</b>
      <p className="req-hint">{t('Schedule days and scope are shown to the client as the proposed impact. Effort hours stay internal.')}</p>
      <div className="crq-row">
        <label>
          {t('Schedule impact (days, minus = earlier)')}
          <input type="number" value={days} onChange={(e) => setDays(e.target.value)} min={-3650} max={3650} step={1} />
        </label>
        <label>
          {t('Effort (hours, internal)')}
          <input type="number" value={hours} onChange={(e) => setHours(e.target.value)} min={0} max={100000} step={1} />
        </label>
      </div>
      <label>
        {t('Scope impact')}
        <textarea value={scope} onChange={(e) => setScope(e.target.value)} rows={2} />
      </label>
      <div className="req-actions">
        <button type="submit" className="btn secondary" disabled={save.isPending}>{save.isPending ? t('Saving…') : t('Save impact')}</button>
      </div>
    </form>
  );
}

function DecisionForm({ cr, projectId }: { cr: StaffCr; projectId: string }) {
  const { t } = usePrefs();
  const toast = useToast();
  const decide = useDecide(projectId, cr);
  const [note, setNote] = useState('');
  const moves = cr.milestone && cr.requested_date;

  const go = (decision: 'approved' | 'declined') =>
    decide.mutate(
      { decision, ...(note.trim() && { note: note.trim() }) },
      {
        onSuccess: () => toast.success(t(decision === 'approved' ? '{code} accepted' : '{code} declined', { code: cr.code })),
        onError: (err) => toast.error(describeApiError(err, t('The decision could not be saved.'))),
      },
    );

  return (
    <div className="crq-decide">
      <b>{t('Decision')}</b>
      <p className="req-hint">
        {moves
          ? t('Accepting moves {code} to {date}. A decision is final.', { code: cr.milestone!.code, date: cr.requested_date! })
          : t('A decision is final and the client sees your note.')}
      </p>
      <label>
        {t('Note (shown to the client)')}
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
      </label>
      <div className="req-actions">
        <button type="button" className="btn" onClick={() => go('approved')} disabled={decide.isPending}>{t('Accept')}</button>
        <button type="button" className="btn secondary" onClick={() => go('declined')} disabled={decide.isPending}>{t('Decline')}</button>
      </div>
    </div>
  );
}

function Conversation({ cr, projectId }: { cr: StaffCr; projectId: string }) {
  const { t } = usePrefs();
  const toast = useToast();
  const comments = useStaffComments(projectId, cr.id);
  const add = useStaffAddComment(projectId, cr.id);
  const [body, setBody] = useState('');
  const [internal, setInternal] = useState(false);

  const send = (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim()) return;
    add.mutate(
      { body: body.trim(), internal },
      {
        onSuccess: () => setBody(''),
        onError: (err) => toast.error(describeApiError(err, t('Your message could not be sent.'))),
      },
    );
  };

  return (
    <>
      <h4>{t('Conversation')}</h4>
      {comments.isError && <p className="field-error" role="alert">{t('The conversation could not be loaded.')}</p>}
      <ul className="crq-thread">
        {comments.data?.map((c) => (
          <li key={c.id} className={c.internal ? 'crq-internal' : c.author_is_client ? 'crq-client' : undefined}>
            <b>{c.author.name}</b>
            {c.internal && <small>{t('Internal note: the client does not see this')}</small>}
            <small>{day(c.created_at)}</small>
            <p>{c.body}</p>
          </li>
        ))}
        {comments.data?.length === 0 && <li>{t('No messages yet.')}</li>}
      </ul>
      <form className="crq-reply" onSubmit={send}>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={2} aria-label={t('Message')} placeholder={t(internal ? 'Write a note for the team' : 'Reply to the client')} />
        <label className="crq-check">
          <input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} />
          {t('Internal note (client does not see it)')}
        </label>
        <div className="req-actions">
          <button type="submit" className="btn" disabled={add.isPending || !body.trim()}>{t('Send')}</button>
        </div>
      </form>
    </>
  );
}
