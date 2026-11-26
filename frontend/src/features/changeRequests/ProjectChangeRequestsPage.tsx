import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Pill, type Tone } from '@/shared/ui/Pill';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { useAuth } from '@/features/auth/AuthContext';
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
  type CrDelivery,
  type StaffCr,
} from './changeRequestsStaffApi';
import '@/features/requirements/requirements.css';
import './changeRequests.css';

// Same wording as the client portal, so both sides name a status the same way.
export const STATUS: Record<CrStatus, { label: string; tone: Tone }> = {
  pending: { label: 'Submitted', tone: 'risk' },
  in_review: { label: 'In review', tone: 'progress' },
  approved: { label: 'Accepted', tone: 'track' },
  declined: { label: 'Declined', tone: 'overdue' },
};
const DELIVERY: Record<CrDelivery, string> = { not_started: 'Not started', in_progress: 'In progress', done: 'Done' };
const FILTERS: (CrStatus | 'all')[] = ['all', 'pending', 'in_review', 'approved', 'declined'];

const day = (stamp: string) => stamp.slice(0, 10);
const daysBetween = (from: string, to: string) => Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000);
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
  const s = STATUS[cr.status];
  return (
    <li className="req-card crq-card">
      <div className="crq-top">
        <span className="crq-ico" aria-hidden="true">⇄</span>
        <div className="crq-main">
          <b>{cr.title}</b>
          <span className="crq-flag">{cr.code} · {t('Submitted')} {day(cr.created_at)}</span>
        </div>
        <Pill tone={s.tone}>{s.label}</Pill>
        <Link className="btn" to={paths.projectChangeRequest(projectId, cr.id)}>{t('Review request')} →</Link>
      </div>
      {cr.status === 'pending' && <div className="crq-await">◷ {t('Awaiting your review')}</div>}
    </li>
  );
}

const REVIEW_LABEL: Record<CrStatus, string> = { pending: 'Pending', in_review: 'Pending', approved: 'Approved', declined: 'Declined' };
const WEEKDAY = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Wed, 25 Nov 2026" from an ISO date. */
const fmtDate = (iso: string) => {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return `${WEEKDAY[d.getUTCDay()]}, ${String(d.getUTCDate()).padStart(2, '0')} ${MONTH[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
};

/** Working days (Mon–Fri) from one date to another; negative when the second date is earlier. */
function workingDaysBetween(from: string, to: string) {
  const sign = to >= from ? 1 : -1;
  const [a, b] = sign === 1 ? [from, to] : [to, from];
  let n = 0;
  for (let t = Date.parse(a) + 86_400_000; t <= Date.parse(b); t += 86_400_000) {
    const wd = new Date(t).getUTCDay();
    if (wd !== 0 && wd !== 6) n++;
  }
  return sign * n;
}

/** The date `n` working days after `from` (ISO). */
function addWorkingDays(from: string, n: number) {
  let t = Date.parse(from.slice(0, 10));
  for (let left = n; left > 0; ) {
    t += 86_400_000;
    const wd = new Date(t).getUTCDay();
    if (wd !== 0 && wd !== 6) left--;
  }
  return new Date(t).toISOString().slice(0, 10);
}

const workingDaysLabel = (n: number) => `${n > 0 ? '+' : ''}${n} working day${Math.abs(n) === 1 ? '' : 's'}`;

export function RequestDetail({ cr, projectId }: { cr: StaffCr; projectId: string }) {
  const { t } = usePrefs();
  const toast = useToast();
  const start = useStartReview(projectId, cr);
  const open = cr.status === 'pending' || cr.status === 'in_review';
  const files = useStaffAttachments(projectId, cr.id);
  const assessed = cr.impact_schedule_value !== null;
  // Choosing a date happens on this page only; once the impact is saved the discussion step takes over.
  const [choosing, setChoosing] = useState(false);
  const [stage, setStage] = useState<'assess' | 'decision'>('assess');
  const recording = cr.status === 'in_review' && assessed && !choosing && stage === 'decision';

  const onAddImpact = () => {
    if (cr.status === 'in_review') return setChoosing(true);
    start.mutate(undefined, {
      onSuccess: () => {
        toast.success(t('{code} is now in review. The client can see this.', { code: cr.code }));
        setChoosing(true);
      },
      onError: (err) => toast.error(describeApiError(err, t('The review could not be started.'))),
    });
  };

  return (
    <div className="crq-grid">
      <div className="crq-col">
        {recording ? (
          <DecisionForm cr={cr} projectId={projectId} onBack={() => setStage('assess')} />
        ) : (
          <>
            <div className="req-card crq-panel">
              <h3>{t('Description')}</h3>
              <p className="crq-desc">{cr.description}</p>
              {cr.reason && <p className="crq-desc"><b>{t('Reason')}:</b> {cr.reason}</p>}
              <p className="crq-flag">
                {t('Submitted')} {fmtDate(cr.created_at)} · {cr.submitted_by.name}{cr.submitted_by_client && ` · ${t('Client')}`}
              </p>
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
                      <small>{f.uploaded_by.name}</small>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="req-card crq-panel">
              <Conversation cr={cr} projectId={projectId} />
            </div>
          </>
        )}
        {cr.status === 'in_review' && assessed && !choosing && stage === 'assess' && (
          <DiscussionPrep cr={cr} projectId={projectId} onSend={() => setStage('decision')} />
        )}
        {!open && <DecisionRecord cr={cr} />}
      </div>

      <div className="crq-col">
        <div className="req-card crq-panel crq-side">
          <h3>{t('Request details')}</h3>
          <div className="crq-line"><span>{t('Status')}</span><Pill tone={STATUS[cr.status].tone}>{REVIEW_LABEL[cr.status]}</Pill></div>
          {cr.decided_by && cr.decided_at && (
            <div className="crq-line"><span>{t('Decided')}</span><b>{cr.decided_by.name} · {fmtDate(cr.decided_at)}</b></div>
          )}
          <hr />
          <p className="crq-eyebrow">{t('Schedule impact')}</p>
          {open && choosing && cr.milestone ? (
            <DatePicker cr={cr} projectId={projectId} onDone={() => setChoosing(false)} />
          ) : open && !assessed ? (
            <>
              <strong className="crq-big">{t('Not assessed')}</strong>
              <p className="req-hint">{t('Delivery dates stay unchanged until approval.')}</p>
              {cr.status === 'in_review' && !cr.milestone ? (
                <ImpactForm cr={cr} projectId={projectId} />
              ) : (
                <div className="req-actions">
                  <button type="button" className="btn" onClick={onAddImpact} disabled={start.isPending}>
                    {start.isPending ? t('Starting…') : t(cr.milestone ? 'Add impact' : 'Start review')}
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              <strong className="crq-big">
                {cr.milestone && cr.requested_date
                  ? t(workingDaysLabel(workingDaysBetween(cr.milestone.due_date, cr.requested_date)))
                  : cr.impact_schedule_value
                    ? t(`{n} ${cr.impact_schedule_unit ?? 'days'}`, { n: cr.impact_schedule_value })
                    : t('No schedule impact')}
              </strong>
              <p className="req-hint">
                {t(cr.status === 'approved' ? 'The approved assessment has been applied.' : cr.status === 'declined' ? 'The original milestone date remains in effect.' : 'Delivery dates stay unchanged until approval.')}
              </p>
              <DateImpact cr={cr} />
              <ImpactSummary cr={cr} />
              {cr.status === 'in_review' && cr.milestone && (
                <div className="req-actions">
                  <button type="button" className="btn secondary" onClick={() => setChoosing(true)}>{t('Change date')}</button>
                </div>
              )}
            </>
          )}
          {cr.delivery && <div className="crq-line"><span>{t('Delivery')}</span><b>{t(DELIVERY[cr.delivery])}</b></div>}
        </div>
      </div>
    </div>
  );
}

/** Pick one of the next working days after the approved date (or no impact); preview, then save. */
function DatePicker({ cr, projectId, onDone }: { cr: StaffCr; projectId: string; onDone: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const save = useSaveImpact(projectId, cr);
  const due = cr.milestone!.due_date;
  const [picked, setPicked] = useState<string | null>(null);
  const options = [addWorkingDays(due, 2), addWorkingDays(due, 3)];

  const commit = () => {
    if (!picked) return;
    const date = picked === 'none' ? null : picked;
    save.mutate(
      {
        impact_schedule_value: date ? daysBetween(due, date) : 0,
        impact_schedule_unit: 'days',
        impact_effort_value: cr.impact_effort_value,
        impact_effort_unit: cr.impact_effort_unit,
        impact_scope: cr.impact_scope,
        requested_date: date,
      },
      {
        onSuccess: () => {
          toast.success(t('Impact saved'));
          onDone();
        },
        onError: (err) => toast.error(describeApiError(err, t('The impact could not be saved.'))),
      },
    );
  };

  if (picked) {
    const date = picked === 'none' ? null : picked;
    return (
      <>
        <strong className="crq-big">{date ? t(workingDaysLabel(workingDaysBetween(due, date))) : t('No schedule impact')}</strong>
        <p className="req-hint">{t('Saving records the proposal. The approved date stays in effect.')}</p>
        <b className="crq-sub">{t('Preview schedule impact')}</b>
        <div className="crq-datelist">
          <div><small>{t('Approved date')}</small><b>{fmtDate(due)}</b></div>
          <div><small>{t('Proposed date')}</small><b>{date ? fmtDate(date) : t('Unchanged')}</b></div>
        </div>
        <div className="req-actions">
          <button type="button" className="btn secondary" onClick={() => setPicked(null)}>{t('Change date')}</button>
          <button type="button" className="btn" onClick={commit} disabled={save.isPending}>{save.isPending ? t('Saving…') : t('Save impact')}</button>
        </div>
      </>
    );
  }

  return (
    <>
      <strong className="crq-big">{t('Propose a new date')}</strong>
      <p className="req-hint">{t('Choose a date to see the change in working days.')}</p>
      <div className="crq-dates"><small>{t('Approved milestone date')}</small><b>{fmtDate(due)}</b></div>
      <b className="crq-sub">{t('Proposed date')}</b>
      <div className="crq-options">
        {options.map((d) => (
          <button key={d} type="button" className="btn secondary" onClick={() => setPicked(d)}>{fmtDate(d)}</button>
        ))}
        <button type="button" className="btn secondary" onClick={() => setPicked('none')}>{t('No schedule impact')}</button>
        <label className="crq-other">
          {t('Other date')}
          <input type="date" min={due} onChange={(e) => e.target.value && setPicked(e.target.value)} />
        </label>
        <button type="button" className="btn secondary" onClick={onDone}>{t('Cancel')}</button>
      </div>
    </>
  );
}

/** Approved milestone date next to the proposed one, so the PM sees what an approval would change. */
function DateImpact({ cr }: { cr: StaffCr }) {
  const { t } = usePrefs();
  if (!cr.milestone) return null;
  const moved = cr.status === 'approved';
  return (
    <div className="crq-datelist">
      <div><small>{t(moved ? 'Previous approved date' : 'Current approved date')}</small><b>{fmtDate(cr.milestone.due_date)}</b></div>
      {cr.requested_date && (
        <div><small>{t(moved ? 'Updated milestone date' : 'Proposed milestone date')}</small><b>{fmtDate(cr.requested_date)}</b></div>
      )}
    </div>
  );
}

function ImpactSummary({ cr }: { cr: StaffCr }) {
  const { t } = usePrefs();
  if (cr.impact_effort_value === null && !cr.impact_scope) return null;
  return (
    <dl className="crq-dl">
      {cr.impact_effort_value !== null && <><dt>{t('Effort')}</dt><dd>{t(`{n} ${cr.impact_effort_unit ?? 'hours'}`, { n: cr.impact_effort_value })}</dd></>}
      {cr.impact_scope && <><dt>{t('Scope impact')}</dt><dd>{cr.impact_scope}</dd></>}
    </dl>
  );
}

/** Fallback for requests with no milestone: schedule days and scope are shared with the client once saved; effort hours stay internal. */
function ImpactForm({ cr, projectId }: { cr: StaffCr; projectId: string }) {
  const { t } = usePrefs();
  const toast = useToast();
  const save = useSaveImpact(projectId, cr);
  const [days, setDays] = useState(cr.impact_schedule_value?.toString() ?? '');
  const [hours, setHours] = useState(cr.impact_effort_value?.toString() ?? '');
  const [scope, setScope] = useState(cr.impact_scope ?? '');

  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(
      {
        impact_schedule_value: num(days),
        impact_schedule_unit: num(days) === null ? null : 'days',
        impact_effort_value: num(hours),
        impact_effort_unit: num(hours) === null ? null : 'hours',
        impact_scope: scope.trim() || null,
        requested_date: null,
      },
      {
        onSuccess: () => toast.success(t('Impact saved')),
        onError: (err) => toast.error(describeApiError(err, t('The impact could not be saved.'))),
      },
    );
  };

  return (
    <form className="crq-impact" onSubmit={submit}>
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
        <button type="submit" className="btn" disabled={save.isPending}>{save.isPending ? t('Saving…') : t('Save impact')}</button>
      </div>
    </form>
  );
}

/** Step after the impact is saved: the two outcomes to put in front of the client. Option B text is stored as the scope impact. */
function DiscussionPrep({ cr, projectId, onSend }: { cr: StaffCr; projectId: string; onSend: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const save = useSaveImpact(projectId, cr);
  const [optionB, setOptionB] = useState(cr.impact_scope ?? '');

  const send = () =>
    save.mutate(
      {
        impact_schedule_value: cr.impact_schedule_value,
        impact_schedule_unit: cr.impact_schedule_unit,
        impact_effort_value: cr.impact_effort_value,
        impact_effort_unit: cr.impact_effort_unit,
        impact_scope: optionB.trim() || null,
        requested_date: cr.requested_date,
      },
      {
        onSuccess: onSend,
        onError: (err) => toast.error(describeApiError(err, t('The assessment could not be saved.'))),
      },
    );

  return (
    <div className="req-card crq-panel crq-form">
      <div>
        <h3 className="crq-h">{t('Prepare the client discussion')}</h3>
        <p className="req-hint">{t('Assessment saved internally. The approved milestone stays in effect.')}</p>
      </div>
      <label>
        {t('Option A · Move the milestone')}
        <input readOnly value={cr.requested_date ? fmtDate(cr.requested_date) : t('Keep the milestone date')} />
      </label>
      <label>
        {t('Option B · Keep the approved date')}
        <textarea value={optionB} onChange={(e) => setOptionB(e.target.value)} rows={2} placeholder={t('How could the team hold the date? For example, defer non-critical items.')} />
      </label>
      <div className="req-actions">
        <button type="button" className="btn" onClick={send} disabled={save.isPending}>{t('Send for client approval')}</button>
      </div>
    </div>
  );
}

/** Records the outcome the client agreed to outside the app. The milestone only moves when approval is recorded. */
function DecisionForm({ cr, projectId, onBack }: { cr: StaffCr; projectId: string; onBack: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const { user } = useAuth();
  const decide = useDecide(projectId, cr);
  const [option, setOption] = useState<'A' | 'B'>('A');
  const [source, setSource] = useState(`${t('Client review meeting')} · ${new Date().toISOString().slice(0, 10)}`);
  const optionText = option === 'A' ? t('A · Extend the milestone') : t('B · Keep the approved date');

  const go = (decision: 'approved' | 'declined') =>
    decide.mutate(
      { decision, note: `${optionText}. ${t('Decision source')}: ${source.trim()}` },
      {
        onSuccess: () => toast.success(t(decision === 'approved' ? '{code} accepted' : '{code} declined', { code: cr.code })),
        onError: (err) => toast.error(describeApiError(err, t('The decision could not be saved.'))),
      },
    );

  return (
    <div className="req-card crq-panel crq-form">
      <div>
        <h3 className="crq-h">{t('Record the client decision')}</h3>
        <p className="req-hint">{t('Use the agreed outcome from the client meeting or email. The milestone changes only when approval is recorded.')}</p>
      </div>
      <div className="req-actions">
        <button type="button" className={`btn secondary${option === 'A' ? ' crq-on' : ''}`} aria-pressed={option === 'A'} onClick={() => setOption('A')}>{t('Select option A')}</button>
        <button type="button" className={`btn secondary${option === 'B' ? ' crq-on' : ''}`} aria-pressed={option === 'B'} onClick={() => setOption('B')}>{t('Select option B')}</button>
      </div>
      <label>{t('Agreed option')}<input readOnly value={optionText} /></label>
      <label>{t('Decision source')}<input value={source} onChange={(e) => setSource(e.target.value)} maxLength={200} /></label>
      <label>{t('Recorded by')}<input readOnly value={user ? `${user.name} · ${t('Project Manager')}` : '—'} /></label>
      <div className="req-actions">
        <button type="button" className="btn secondary" onClick={onBack}>{t('Back to assessment')}</button>
        <button type="button" className="btn secondary" onClick={() => go('declined')} disabled={decide.isPending || !source.trim()}>{t('Record rejection')}</button>
        <button type="button" className="btn" onClick={() => go('approved')} disabled={decide.isPending || !source.trim()}>{t('Record approval')}</button>
      </div>
    </div>
  );
}

/** Read-only summary once a decision exists. */
function DecisionRecord({ cr }: { cr: StaffCr }) {
  const { t } = usePrefs();
  const [outcome, source] = (cr.decision_note ?? '').split(`. ${t('Decision source')}: `);
  return (
    <div className="req-card crq-panel crq-form">
      <div>
        <h3 className="crq-h">{t('Client decision recorded')}</h3>
        <p className="req-hint">{t(cr.status === 'approved' ? 'Approved' : 'Rejected')}</p>
      </div>
      {source !== undefined ? (
        <>
          <label>{t('Agreed option')}<input readOnly value={outcome} /></label>
          <label>{t('Decision source')}<input readOnly value={source} /></label>
        </>
      ) : (
        cr.decision_note && <label>{t('Decision note')}<input readOnly value={cr.decision_note} /></label>
      )}
      <label>{t('Recorded by')}<input readOnly value={cr.decided_by?.name ?? '—'} /></label>
    </div>
  );
}

const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
const stamp = (iso: string) => `${new Date(iso).getDate()} ${MONTH[new Date(iso).getMonth()]}, ${new Date(iso).toTimeString().slice(0, 5)}`;

/** Comments the client sees: one line per message, then a single composer. */
function Conversation({ cr, projectId }: { cr: StaffCr; projectId: string }) {
  const { t } = usePrefs();
  const toast = useToast();
  const comments = useStaffComments(projectId, cr.id);
  const add = useStaffAddComment(projectId, cr.id);
  const [body, setBody] = useState('');

  const send = (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim()) return;
    add.mutate(
      { body: body.trim(), internal: false },
      {
        onSuccess: () => setBody(''),
        onError: (err) => toast.error(describeApiError(err, t('Your message could not be sent.'))),
      },
    );
  };

  return (
    <>
      <h3>{t('Comments')}</h3>
      {comments.isError && <p className="field-error" role="alert">{t('The conversation could not be loaded.')}</p>}
      <ul className="crq-thread">
        {comments.data?.map((c) => (
          <li key={c.id} className={c.internal ? 'crq-internal' : undefined}>
            <span className="crq-av" aria-hidden="true">{c.author_is_client ? 'CL' : initials(c.author.name)}</span>
            <div>
              <small>{c.author_is_client ? t('Client contact') : c.author.name} · {stamp(c.created_at)}{c.internal && ` · ${t('Internal note: the client does not see this')}`}</small>
              <p>{c.body}</p>
            </div>
          </li>
        ))}
      </ul>
      <form className="crq-reply" onSubmit={send}>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={2} aria-label={t('Message')} placeholder={t('Write a comment…')} />
        <button type="submit" className="crq-send" aria-label={t('Send')} disabled={add.isPending || !body.trim()}>↑</button>
      </form>
      <small className="crq-flag">{t('Comments are visible to the client.')}</small>
    </>
  );
}
