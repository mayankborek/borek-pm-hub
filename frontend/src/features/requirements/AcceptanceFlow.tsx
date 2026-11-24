import { useState } from 'react';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { useAuth } from '@/features/auth/AuthContext';
import { DECISION_LABEL, usePublishRequirement, type Requirement } from './requirementsApi';

/**
 * PM acceptance flow for one requirement, from borek-flow-screens: internal review, client preview,
 * publish, then tracking and the recorded acceptance. Corrections reuse the requirement's edit form.
 */
type Step = 'review' | 'preview' | 'publish';

const day = (stamp: string) => stamp.slice(0, 10);

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="acc-field">
      <span className="acc-lbl">{label}</span>
      <div className="acc-val">{children}</div>
    </div>
  );
}

export function AcceptanceFlow({ requirement: r, projectId, onCorrect }: { requirement: Requirement; projectId: string; onCorrect: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const { user } = useAuth();
  const publish = usePublishRequirement(projectId);
  const [step, setStep] = useState<Step>('review');
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  const draft = r.versions[0];
  const closed = r.status === 'accepted' || r.status === 'rejected';
  const inReview = !closed && draft?.state === 'draft';

  if (inReview) {
    const criteria = draft.acceptance_criteria;
    const ready = criteria.every((c) => checked[c]);
    const meta = [r.code, r.milestone?.code].filter(Boolean).join(' · ');

    const onPublish = () =>
      publish.mutate(r, {
        onSuccess: () => {
          toast.success(t('{code} v{n} sent to the client for acceptance', { code: r.code, n: r.current_version }));
          setStep('review');
        },
        onError: (err) => toast.error(describeApiError(err, t('The requirement could not be published.'))),
      });

    if (step === 'preview') {
      return (
        <div className="acc">
          <div className="acc-banner">
            <b className="acc-blue">{t('Client preview')}</b>
            <p>{t('Review the exact content the client will receive. Internal notes stay private.')}</p>
          </div>
          <div className="acc-card">
            <h4>{r.code} · {r.title}</h4>
            <p className="acc-sub">{t('Version {n}', { n: draft.number })}</p>
            <h5>{t('Description')}</h5>
            <p>{draft.description}</p>
            {criteria.length > 0 && (
              <>
                <h5>{t('Acceptance criteria')}</h5>
                <ul>{criteria.map((c) => <li key={c}>{c}</li>)}</ul>
              </>
            )}
          </div>
          <div className="req-actions acc-end">
            <button type="button" className="btn secondary" onClick={() => setStep('review')}>{t('Back to review')}</button>
            <button type="button" className="btn" onClick={() => setStep('publish')}>{t('Continue to publish')}</button>
          </div>
        </div>
      );
    }

    if (step === 'publish') {
      return (
        <div className="acc">
          <div className="acc-card">
            <h4>{t('Publish deliverable for acceptance')}</h4>
            <p className="acc-sub">{t('Only the reviewed content is shared with the client.')}</p>
            <Field label={t('Deliverable')}>{r.code} · {r.title}</Field>
            <Field label={t('Version')}>{draft.number}</Field>
            <Field label={t('Included')}>{draft.description}</Field>
          </div>
          <div className="req-actions acc-end">
            <button type="button" className="btn secondary" onClick={() => setStep('preview')} disabled={publish.isPending}>{t('Back to preview')}</button>
            <button type="button" className="btn" onClick={onPublish} disabled={publish.isPending}>
              {publish.isPending ? t('Publishing…') : t('Publish for acceptance')}
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="acc">
        <div className="acc-card">
          <h4>{t('Internal review')} · {r.title}</h4>
          <p className="acc-sub">{meta}</p>
          <p className="acc-sub">{t('Version {n}', { n: draft.number })}</p>
          <h5>{t('Review checklist')}</h5>
          {criteria.length === 0 ? (
            <p className="acc-sub">{t('No acceptance criteria to check.')}</p>
          ) : (
            <ul className="acc-checks">
              {criteria.map((c) => (
                <li key={c}>
                  <label>
                    <input type="checkbox" checked={!!checked[c]} onChange={(e) => setChecked((s) => ({ ...s, [c]: e.target.checked }))} />
                    {c}
                  </label>
                </li>
              ))}
            </ul>
          )}
          <Field label={t('Reviewer')}>{user?.name} · {t('Project Manager')}</Field>
        </div>
        <div className="req-actions acc-end">
          <button type="button" className="btn secondary" onClick={onCorrect}>{t('Request corrections')}</button>
          <button type="button" className="btn" onClick={() => setStep('preview')} disabled={!ready}>{t('Ready for client')}</button>
        </div>
      </div>
    );
  }

  // Nothing waiting for review: track the version on the client's desk.
  const sent = r.versions.find((v) => v.number === r.published_version);
  if (!sent) return null;

  if (sent.response && sent.responded_at) {
    const accepted = sent.response === 'accepted';
    return (
      <div className="acc">
        <div className="acc-banner">
          <b className={accepted ? 'acc-green' : 'acc-blue'}>
            {accepted ? t('Client acceptance recorded') : t('Client response recorded: {decision}', { decision: t(DECISION_LABEL[sent.response]) })}
          </b>
          <p>{t('The client answered the delivery identified in this record.')}</p>
        </div>
        <p className="acc-sub">{t('Answered version: {n}', { n: sent.number })}</p>
        <div className="acc-card">
          <h4>{t('Acceptance record')}</h4>
          <p className="acc-sub">{t('The answer is attached to the published version.')}</p>
          <Field label={t('Deliverable')}>{r.code} · {r.title}</Field>
          <Field label={t('Answered by')}>{sent.responded_by?.name} · {day(sent.responded_at)}</Field>
          {sent.response_comment && <Field label={t('Note')}>{sent.response_comment}</Field>}
          {r.milestone && <Field label={t('Milestone')}>{r.milestone.code} · {r.milestone.name}</Field>}
        </div>
      </div>
    );
  }

  return (
    <div className="acc">
      <div className="acc-card">
        <h4>{t('Client acceptance')}</h4>
        <p className="acc-sub">{t('Client responses apply only to the published delivery shown here.')}</p>
        <p className="acc-status">{t('Awaiting client response')}</p>
        <p className="acc-sub">
          {t('Version {n}', { n: sent.number })}
          {sent.published_at && <> · {t('Published {date}', { date: day(sent.published_at) })}</>}
          {sent.published_by && <> · {sent.published_by.name}</>}
        </p>
      </div>
    </div>
  );
}
