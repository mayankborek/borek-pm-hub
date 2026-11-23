import { useState, type FormEvent } from 'react';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Pill, type Tone } from '@/shared/ui/Pill';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { useProjectContext } from '@/features/projects/ProjectLayout';
import {
  DECISION_LABEL,
  STATUS,
  VERSION_STATE_LABEL,
  useCreateRequirement,
  usePublishRequirement,
  useRequirements,
  useUpdateRequirement,
  type Requirement,
  type RequirementDraft,
  type RequirementStatus,
} from './requirementsApi';
import './requirements.css';

const PILL: Record<RequirementStatus, Tone> = {
  draft: 'neutral',
  awaiting_acceptance: 'risk',
  changes_requested: 'progress',
  accepted: 'track',
  rejected: 'overdue',
};
const FILTERS: (RequirementStatus | 'all')[] = ['all', 'draft', 'awaiting_acceptance', 'changes_requested', 'accepted', 'rejected'];

const day = (stamp: string) => stamp.slice(0, 10);
const toCriteria = (text: string) => text.split('\n').map((l) => l.trim()).filter(Boolean);

/** Requirements tab: create and publish requirements for client acceptance, and track the answers. */
export function ProjectRequirementsPage() {
  const project = useProjectContext();
  const { t } = usePrefs();
  const list = useRequirements(project.id);
  const [filter, setFilter] = useState<RequirementStatus | 'all'>('all');
  const [composing, setComposing] = useState(false);

  if (list.isError) return <ErrorState title="We couldn’t load the requirements" onRetry={() => void list.refetch()} />;
  if (!list.data) return <LoadingState title="Loading requirements" />;

  const { items, counts } = list.data;
  const shown = filter === 'all' ? items : items.filter((r) => r.status === filter);

  return (
    <section className="req" aria-label={t('Requirements')}>
      <div className="req-head">
        <p>{t('Publish a requirement for the client to accept, then follow their answer here.')}</p>
        {!composing && (
          <button type="button" className="btn" onClick={() => setComposing(true)}>
            {t('New requirement')}
          </button>
        )}
      </div>

      {composing && <RequirementForm projectId={project.id} onDone={() => setComposing(false)} />}

      <div className="req-filters" role="tablist" aria-label={t('Filter by status')}>
        {FILTERS.map((f) => (
          <button key={f} type="button" role="tab" aria-selected={filter === f} className={filter === f ? 'req-on' : undefined} onClick={() => setFilter(f)}>
            {t(f === 'all' ? 'All' : STATUS[f].label)} <span>{f === 'all' ? (counts.total ?? items.length) : (counts[f] ?? 0)}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <EmptyState
          title={items.length === 0 ? 'No requirements yet' : 'Nothing with this status'}
          text={items.length === 0 ? 'Use “New requirement” to add the first one.' : 'Choose another status to see more.'}
        />
      ) : (
        <ul className="req-list">
          {shown.map((r) => <RequirementCard key={r.id} requirement={r} projectId={project.id} />)}
        </ul>
      )}
    </section>
  );
}

function RequirementForm({ projectId, requirement, onDone }: { projectId: string; requirement?: Requirement; onDone: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const create = useCreateRequirement(projectId);
  const update = useUpdateRequirement(projectId, requirement as Requirement);
  const latest = requirement?.versions[0];
  const [title, setTitle] = useState(requirement?.title ?? '');
  const [description, setDescription] = useState(latest?.description ?? '');
  const [criteria, setCriteria] = useState(latest?.acceptance_criteria.join('\n') ?? '');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string>();
  const pending = create.isPending || update.isPending;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(undefined);
    if (!title.trim() || !description.trim()) return setError(t('Add a title and a description.'));
    const draft: RequirementDraft = { title: title.trim(), description: description.trim(), acceptance_criteria: toCriteria(criteria) };
    const opts = {
      onSuccess: () => {
        toast.success(t(requirement ? 'Requirement saved' : 'Requirement created'));
        onDone();
      },
      onError: (err: unknown) => setError(describeApiError(err, t('The requirement could not be saved.'))),
    };
    if (requirement) update.mutate({ ...draft, ...(note.trim() && { change_note: note.trim() }) }, opts);
    else create.mutate(draft, opts);
  };

  return (
    <form className="req-form" onSubmit={submit} noValidate>
      <h3>{t(requirement ? 'Edit requirement' : 'New requirement')}</h3>
      {requirement && latest?.published_at && (
        <p className="req-hint">{t('Changing the content starts a new draft version. The client keeps seeing the published one until you publish.')}</p>
      )}
      <div className="field">
        <label htmlFor="req-title">{t('Title')}</label>
        <input id="req-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required />
      </div>
      <div className="field">
        <label htmlFor="req-desc">{t('Description')}</label>
        <textarea id="req-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={4} required />
      </div>
      <div className="field">
        <label htmlFor="req-crit">{t('Acceptance criteria (one per line)')}</label>
        <textarea id="req-crit" value={criteria} onChange={(e) => setCriteria(e.target.value)} rows={4} />
      </div>
      {requirement && (
        <div className="field">
          <label htmlFor="req-note">{t('What changed? (shown to the client)')}</label>
          <textarea id="req-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
        </div>
      )}
      {error && <p className="field-error" role="alert">{error}</p>}
      <div className="req-actions">
        <button type="submit" className="btn" disabled={pending}>{pending ? t('Saving…') : t('Save')}</button>
        <button type="button" className="btn secondary" onClick={onDone} disabled={pending}>{t('Cancel')}</button>
      </div>
    </form>
  );
}

function RequirementCard({ requirement: r, projectId }: { requirement: Requirement; projectId: string }) {
  const { t } = usePrefs();
  const toast = useToast();
  const publish = usePublishRequirement(projectId);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);

  const newest = r.versions[0];
  const closed = r.status === 'accepted' || r.status === 'rejected';
  // Publish is offered when the newest version is a draft; the one on the client's desk is `published_version`.
  const canPublish = !closed && newest?.state === 'draft';
  const shownVersion = r.published_version ?? r.current_version;

  const onPublish = () =>
    publish.mutate(r, {
      onSuccess: () => toast.success(t('{code} v{n} sent to the client for acceptance', { code: r.code, n: r.current_version })),
      onError: (err) => toast.error(describeApiError(err, t('The requirement could not be published.'))),
    });

  return (
    <li className="req-card">
      <button type="button" className="req-summary" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="req-code">{r.code}</span>
        <b>{r.title}</b>
        <span className="req-ver">v{shownVersion}</span>
        <Pill tone={PILL[r.status]}>{STATUS[r.status].label}</Pill>
      </button>
      {open && (
        <div className="req-detail">
          {r.has_unpublished_changes && <p className="req-hint">{t('Version {n} is a draft: the client still sees v{m}.', { n: r.current_version, m: r.published_version ?? '' })}</p>}
          <div className="req-actions">
            {canPublish && (
              <button type="button" className="btn" onClick={onPublish} disabled={publish.isPending}>
                {publish.isPending ? t('Publishing…') : t('Publish v{n} for acceptance', { n: r.current_version })}
              </button>
            )}
            {!closed && !editing && <button type="button" className="btn secondary" onClick={() => setEditing(true)}>{t('Edit')}</button>}
          </div>
          {editing && <RequirementForm projectId={projectId} requirement={r} onDone={() => setEditing(false)} />}
          <ol className="req-versions">
            {r.versions.map((v) => (
              <li key={v.number}>
                <div className="req-vhead">
                  <b>v{v.number}</b>
                  <span>{t(VERSION_STATE_LABEL[v.state])}</span>
                  {v.published_at && <small>{t('Published {date}', { date: day(v.published_at) })}</small>}
                </div>
                <p>{v.description}</p>
                {v.change_note && <p className="req-note">{t('Changed: {note}', { note: v.change_note })}</p>}
                {v.acceptance_criteria.length > 0 && (
                  <ul>{v.acceptance_criteria.map((c) => <li key={c}>{c}</li>)}</ul>
                )}
                {v.response && v.responded_at && (
                  <p className="req-answer">
                    <b>{t(DECISION_LABEL[v.response])}</b> · {v.responded_by?.name} · {day(v.responded_at)}
                    {v.response_comment && <> — {v.response_comment}</>}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </li>
  );
}
