import { useState, type FormEvent } from 'react';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { useProjectContext } from '@/features/client/ClientProjectLayout';
import { useApiProjectId } from '@/features/client/changeRequestsApi';
import { Badge, EmptyCard, ErrorCard, LoadingCard } from '@/features/client/ui';
import type { Tone } from '@/features/client/labels';
import {
  DECISION_LABEL,
  STATUS,
  useClientRequirements,
  useRespond,
  type ClientRequirement,
  type ClientVersion,
  type Decision,
} from './requirementsApi';
import './requirements.css';

const DECISIONS: Decision[] = ['accepted', 'changes_requested', 'rejected'];
const day = (stamp: string) => stamp.slice(0, 10);

/** Client Requirements: review the published version of each requirement and record the answer. */
export function ClientRequirementsPage() {
  const { t } = usePrefs();
  const { project } = useProjectContext();
  const real = useApiProjectId(project);
  const list = useClientRequirements(real.id);

  if (real.missing) {
    return <EmptyCard title="Requirements are not available" text="This project is not connected to the portal service yet." />;
  }
  if (real.isError || list.isError) return <ErrorCard onRetry={() => (real.isError ? window.location.reload() : void list.refetch())} />;
  if (!list.data || !real.id) return <LoadingCard />;

  const { items } = list.data;
  return (
    <section className="req" aria-label={t('Requirements')}>
      <div className="req-head">
        <div>
          <h2>{t('Requirements')}</h2>
          <p>{t('Review each requirement your project team publishes and tell them whether you accept it.')}</p>
        </div>
      </div>
      {items.length === 0 ? (
        <EmptyCard title="No requirements to review" text="Requirements appear here when your Project Manager publishes them for acceptance." />
      ) : (
        <ul className="req-list">
          {items.map((r) => <RequirementCard key={r.id} requirement={r} projectId={real.id!} />)}
        </ul>
      )}
    </section>
  );
}

const TONE: Record<string, Tone> = { awaiting_acceptance: 'warning', changes_requested: 'info', accepted: 'success', rejected: 'danger' };

function RequirementCard({ requirement: r, projectId }: { requirement: ClientRequirement; projectId: string }) {
  const { t } = usePrefs();
  const [open, setOpen] = useState(r.awaiting_your_answer);
  return (
    <li className="req-card">
      <button type="button" className="req-summary" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="req-code">{r.code}</span>
        <b>{r.title}</b>
        <span className="req-ver">v{r.current.number}</span>
        <Badge tone={TONE[r.status]}>{t(STATUS[r.status].label)}</Badge>
      </button>
      {open && (
        <div className="req-detail">
          <VersionView version={r.current} />
          {r.awaiting_your_answer && <AnswerForm projectId={projectId} requirementId={r.id} version={r.current.number} />}
          {r.history.length > 0 && (
            <>
              <h4>{t('Earlier versions')}</h4>
              <ol className="req-versions">
                {r.history.map((v) => <li key={v.number}><VersionView version={v} /></li>)}
              </ol>
            </>
          )}
        </div>
      )}
    </li>
  );
}

function VersionView({ version: v }: { version: ClientVersion }) {
  const { t } = usePrefs();
  return (
    <>
      <div className="req-vhead">
        <b>v{v.number}</b>
        <small>{t('Published {date}', { date: day(v.published_at) })}</small>
      </div>
      <p>{v.description}</p>
      {v.change_note && <p className="req-note">{t('Changed: {note}', { note: v.change_note })}</p>}
      {v.acceptance_criteria.length > 0 && (
        <>
          <h4>{t('Acceptance criteria')}</h4>
          <ul>{v.acceptance_criteria.map((c) => <li key={c}>{c}</li>)}</ul>
        </>
      )}
      {v.response && v.responded_at && (
        <p className="req-answer">
          <b>{t(DECISION_LABEL[v.response])}</b> · {v.responded_by} · {day(v.responded_at)}
          {v.response_comment && <> — {v.response_comment}</>}
        </p>
      )}
    </>
  );
}

/** Answers the exact version on screen: the server refuses it if a newer one was published meanwhile. */
function AnswerForm({ projectId, requirementId, version }: { projectId: string; requirementId: string; version: number }) {
  const { t } = usePrefs();
  const toast = useToast();
  const respond = useRespond(projectId, requirementId);
  const [decision, setDecision] = useState<Decision>('accepted');
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string>();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(undefined);
    if (decision !== 'accepted' && !comment.trim()) return setError(t('Say what should change, or why it is rejected.'));
    respond.mutate(
      { version_number: version, decision, ...(comment.trim() && { comment: comment.trim() }) },
      {
        onSuccess: () => toast.success(t('Your answer was sent to your project team')),
        onError: (err) => setError(describeApiError(err, t('Your answer could not be sent.'))),
      },
    );
  };

  return (
    <form className="req-form" onSubmit={submit} noValidate>
      <h4>{t('Your answer to v{n}', { n: version })}</h4>
      <fieldset>
        <legend className="req-sr">{t('Decision')}</legend>
        {DECISIONS.map((d) => (
          <label key={d} className="req-radio">
            <input type="radio" name={`decision-${requirementId}`} checked={decision === d} onChange={() => setDecision(d)} />
            {t(DECISION_LABEL[d])}
          </label>
        ))}
      </fieldset>
      <label>
        {t(decision === 'accepted' ? 'Comment (optional)' : 'Comment (required)')}
        <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={3} />
      </label>
      {error && <p className="req-error" role="alert">{error}</p>}
      <div className="req-actions">
        <button type="submit" className="req-btn" disabled={respond.isPending}>{respond.isPending ? t('Sending…') : t('Send answer')}</button>
      </div>
    </form>
  );
}
