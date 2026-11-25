import { useEffect, useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { parseApiError } from '@/features/projects/projectsApi';
import { useProjectContext } from '@/features/projects/ProjectLayout';
import { formatDate } from '@/features/projects/projectUi';
import { useProjectMembers } from '@/features/tasks/tasksApi';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useCreateMilestone, useRoadmap, type Milestone, type Roadmap } from './milestonesApi';
import './milestones.css';

const DAY = 86_400_000;
const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / DAY;
const iso = (d: number) => new Date(d * DAY).toISOString().slice(0, 10);
const short = (s: string) => formatDate(s).replace(/ \d{4}$/, '');

const PHASE_LABEL = { not_started: 'Not started', in_progress: 'In progress', completed: 'Completed' } as const;

/** Milestones tab (Figma "Milestones"): phases as bars on a timeline, milestones as diamonds, today as a line. */
export function MilestonesPage() {
  const project = useProjectContext();
  const { user } = useAuth();
  const { t } = usePrefs();
  const roadmap = useRoadmap(project.id);
  const [creating, setCreating] = useState(false);
  if (user?.role !== 'pm') return <Navigate to={paths.project(project.id)} replace />;

  if (roadmap.isPending) return <LoadingState title={t('Loading roadmap')} text={t('Fetching phases and milestones.')} />;
  if (roadmap.isError) return <ErrorState title={t('We couldn’t load the roadmap')} text={t('Check your connection and try again.')} onRetry={() => void roadmap.refetch()} />;
  const r = roadmap.data;

  return (
    <section className="ms" aria-label={t('Project roadmap')}>
      <header className="ms-head">
        <div>
          <h2>{t('Project roadmap')}</h2>
          <p>{t('Project phases and delivery milestones')}{r.range_start && r.range_end ? ` · ${short(r.range_start)}–${formatDate(r.range_end)}` : ''}</p>
        </div>
        <button type="button" className="btn" onClick={() => setCreating(true)}>{t('Create milestone')}</button>
      </header>
      <Timeline r={r} />
      <ul className="ms-legend">
        <li><i className="done" />{t('Completed share')}</li>
        <li><i className="rest" />{t('Remaining work')}</li>
        <li><i className="dia on" />{t('Milestone reached')}</li>
        <li><i className="dia" />{t('Milestone ahead')}</li>
        <li><i className="today" />{t('Today')}</li>
      </ul>
      <p className="ms-note">{t('Phase bars show duration. Diamonds mark milestone due dates. Progress comes from linked tasks.')}</p>
      {creating && <NewMilestone projectId={project.id} r={r} onClose={() => setCreating(false)} />}
    </section>
  );
}

function Timeline({ r }: { r: Roadmap }) {
  const { t } = usePrefs();
  const all = [...r.phases.flatMap((p) => [p.start_date, p.end_date, ...p.milestones.map((m) => m.due_date)]), ...r.unphased_milestones.map((m) => m.due_date), r.today];
  if (r.phases.length === 0 && r.unphased_milestones.length === 0) {
    return <p className="ms-empty">{t('No phases or milestones yet. Create a milestone to start the roadmap.')}</p>;
  }
  const start = Math.min(...all.map(day), r.range_start ? day(r.range_start) : Infinity);
  const end = Math.max(...all.map(day), r.range_end ? day(r.range_end) : -Infinity);
  const span = Math.max(end - start, 1);
  const pos = (d: string) => `${((day(d) - start) / span) * 100}%`;
  const ticks = Array.from({ length: 5 }, (_, i) => iso(start + (span * i) / 4));

  const diamond = (m: Milestone) => (
    <div className="ms-dia" key={m.id} style={{ left: pos(m.due_date) }}>
      <i className={m.done ? 'on' : ''} />
      <span className="ms-dia-name">{m.name}</span>
      <span className={`ms-dia-date${m.state === 'late' ? ' late' : ''}`}>{short(m.due_date)}{m.state === 'late' ? ` · ${t('Running late')}` : ''}</span>
    </div>
  );

  return (
    <div className="ms-chart">
      <div className="ms-axis">
        {ticks.map((d) => (
          <span key={d} style={{ left: `calc(var(--ms-label) + (100% - var(--ms-label)) * ${(day(d) - start) / span})` }}>{short(d)}</span>
        ))}
      </div>
      {r.phases.map((p) => (
        <div className="ms-row" key={p.id}>
          <div className="ms-label"><b>{p.name}</b><span>{p.is_late ? t('Running late') : t(PHASE_LABEL[p.status])}</span></div>
          <div className="ms-track">
            <div className="ms-bar" style={{ left: pos(p.start_date), width: `calc(${pos(p.end_date)} - ${pos(p.start_date)})` }}>
              <i style={{ width: `${p.status === 'completed' ? 100 : p.progress ?? 0}%` }} />
            </div>
            {p.milestones.map(diamond)}
          </div>
        </div>
      ))}
      {r.unphased_milestones.length > 0 && (
        <div className="ms-row">
          <div className="ms-label"><b>{t('Other milestones')}</b><span>{t('Not in a phase')}</span></div>
          <div className="ms-track">{r.unphased_milestones.map(diamond)}</div>
        </div>
      )}
      <div className="ms-today" style={{ left: `calc(var(--ms-label) + (100% - var(--ms-label)) * ${(day(r.today) - start) / span})` }}>
        <span>{t('Today')} · {short(r.today)}</span>
      </div>
    </div>
  );
}

/** Figma "New milestone": title, phase, status, due date, owner, client visibility. The backend keeps a single due date per milestone. */
function NewMilestone({ projectId, r, onClose }: { projectId: string; r: Roadmap; onClose: () => void }) {
  const { t } = usePrefs();
  const create = useCreateMilestone(projectId);
  const members = useProjectMembers(projectId);
  const [form, setForm] = useState({ name: '', phase_id: '', status: 'planned', due_date: '', owner_id: '', client_visible: true });
  const [error, setError] = useState('');
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.due_date) return setError(t('Enter a title and a date.'));
    create.mutate(
      { name: form.name.trim(), due_date: form.due_date, phase_id: form.phase_id || null, owner_id: form.owner_id || null, at_risk: form.status === 'at_risk', client_visible: form.client_visible },
      { onSuccess: onClose, onError: (err) => setError(parseApiError(err).message) },
    );
  };

  return (
    <div className="ms-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="ms-dialog" role="dialog" aria-modal="true" aria-labelledby="ms-new" onSubmit={submit} noValidate>
        <header><h3 id="ms-new">{t('New milestone')}</h3><button type="button" aria-label={t('Close')} onClick={onClose}>×</button></header>
        {error && <div className="form-alert" role="alert">{error}</div>}
        <div className="field"><label htmlFor="ms-title">{t('Title')}</label><input id="ms-title" className="input" autoFocus placeholder={t('Enter milestone name')} value={form.name} onChange={(e) => set('name', e.target.value)} /></div>
        <div className="ms-two">
          <div className="field"><label htmlFor="ms-phase">{t('Phase')}</label>
            <select id="ms-phase" className="input" value={form.phase_id} onChange={(e) => set('phase_id', e.target.value)}>
              <option value="">{t('No phase')}</option>
              {r.phases.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select></div>
          <div className="field"><label htmlFor="ms-status">{t('Status')}</label>
            <select id="ms-status" className="input" value={form.status} onChange={(e) => set('status', e.target.value)}>
              <option value="planned">{t('Planned')}</option>
              <option value="at_risk">{t('At risk')}</option>
            </select></div>
          <div className="field"><label htmlFor="ms-due">{t('Due date')}</label><input id="ms-due" type="date" className="input" value={form.due_date} onChange={(e) => set('due_date', e.target.value)} /></div>
          <div className="field"><label htmlFor="ms-owner">{t('Owner')}</label>
            <select id="ms-owner" className="input" value={form.owner_id} onChange={(e) => set('owner_id', e.target.value)}>
              <option value="">{t('Unassigned')}</option>
              {(members.data ?? []).map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
            </select></div>
        </div>
        <label className="ms-check"><input type="checkbox" checked={form.client_visible} onChange={(e) => set('client_visible', e.target.checked)} />{t('Visible to the client')}</label>
        <footer>
          <button type="button" className="btn secondary" onClick={onClose}>{t('Cancel')}</button>
          <button type="submit" className="btn" disabled={create.isPending}>{t(create.isPending ? 'Creating…' : 'Create')}</button>
        </footer>
      </form>
    </div>
  );
}
