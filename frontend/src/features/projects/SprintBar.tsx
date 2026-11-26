import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/features/auth/AuthContext';
import { api, describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { emptyFilter, useProjectTasks } from '@/features/tasks/tasksApi';
import { formatDate } from './projectUi';
import './sprintBar.css';

/** Mirrors the fields of backend SprintOut that the bar shows. */
interface Sprint {
  id: string;
  name: string;
  state: 'planned' | 'active' | 'completed';
  start_date: string | null;
  end_date: string | null;
  version: number;
}

const sprintKey = (projectId: string) => ['projects', 'sprints', projectId] as const;

const Icon = ({ d }: { d: string }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={d} />
  </svg>
);
const EDIT = 'M4 20l1-5L16 4l4 4L9 19z';
const ARCHIVE = 'M3 4h18v4H3zM5 8v12h14V8M10 12h4';
const TRASH = 'M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7';

const range = (s: Sprint) => `${formatDate(s.start_date)} – ${formatDate(s.end_date)}`;

/** Add tasks to a planned sprint: pick from the tasks still in the backlog. */
function AddTasks({ projectId, sprint, onDone }: { projectId: string; sprint: Sprint; onDone: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const qc = useQueryClient();
  const tasks = useProjectTasks(projectId, { ...emptyFilter, category: 'backlog' });
  const [picked, setPicked] = useState<string[]>([]);
  const move = useMutation({
    mutationFn: () => api(`/projects/${projectId}/sprints/move-tasks`, { method: 'POST', body: JSON.stringify({ task_ids: picked, sprint_id: sprint.id }) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['tasks'] });
      void qc.invalidateQueries({ queryKey: sprintKey(projectId) });
      onDone();
    },
    onError: (e) => toast.error(describeApiError(e, t('Could not add the tasks.'))),
  });
  const items = tasks.data?.items ?? [];
  return (
    <div className="ms-add">
      <b>{t('Add tasks to {name}', { name: sprint.name })}</b>
      {items.length === 0 ? (
        <p>{t('No backlog tasks to add.')}</p>
      ) : (
        <ul>
          {items.map((k) => (
            <li key={k.id}>
              <label>
                <input type="checkbox" checked={picked.includes(k.id)} onChange={(e) => setPicked((p) => (e.target.checked ? [...p, k.id] : p.filter((id) => id !== k.id)))} />
                {k.key} · {k.title}
              </label>
            </li>
          ))}
        </ul>
      )}
      <div className="ms-add-acts">
        <button type="button" className="btn" onClick={onDone}>{t('Cancel')}</button>
        <button type="button" className="btn primary" disabled={!picked.length || move.isPending} onClick={() => move.mutate()}>{t('Add tasks')}</button>
      </div>
    </div>
  );
}

/** One row of the Manage sprints table, switching to inline fields while editing. */
function SprintRow({ projectId, sprint, onChange }: { projectId: string; sprint: Sprint; onChange: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: sprint.name, start_date: sprint.start_date ?? '', end_date: sprint.end_date ?? '' });
  const fail = (e: unknown) => toast.error(describeApiError(e, t('Could not update the sprint.')));
  const base = `/projects/${projectId}/sprints/${sprint.id}`;
  const save = useMutation({
    mutationFn: () =>
      api(base, { method: 'PATCH', body: JSON.stringify({ version: sprint.version, name: form.name.trim(), start_date: form.start_date || null, end_date: form.end_date || null }) }),
    onSuccess: () => {
      setEditing(false);
      onChange();
    },
    onError: fail,
  });
  const start = useMutation({
    mutationFn: () => api(`${base}/start`, { method: 'POST', body: JSON.stringify({ version: sprint.version }) }),
    onSuccess: onChange,
    onError: fail,
  });
  const archive = useMutation({ mutationFn: () => api(base, { method: 'DELETE' }), onSuccess: onChange, onError: fail });
  const remove = () => {
    if (window.confirm(t('Remove {name}? Its tasks go back to the backlog.', { name: sprint.name }))) archive.mutate();
  };

  return (
    <>
      <div className="sr">
        <div>
          {editing ? (
            <div className="sr-edit">
              <input aria-label={t('Sprint name')} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <input type="date" aria-label={t('Start date')} value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
              <input type="date" aria-label={t('End date')} min={form.start_date || undefined} value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
            </div>
          ) : (
            <>
              <b>{sprint.name}</b>
              <small>{range(sprint)}</small>
            </>
          )}
        </div>
        <div>
          <span className={sprint.state === 'active' ? 'badge active' : 'badge'}>{t(sprint.state === 'active' ? 'Active' : 'Planned')}</span>
        </div>
        <div className="acts">
          {editing ? (
            <>
              <button type="button" className="btn" onClick={() => setEditing(false)}>{t('Cancel')}</button>
              <button type="button" className="btn primary" disabled={!form.name.trim() || save.isPending} onClick={() => save.mutate()}>{t('Save')}</button>
            </>
          ) : (
            <>
              <button type="button" className="e" aria-label={t('Edit {name}', { name: sprint.name })} onClick={() => setEditing(true)}><Icon d={EDIT} /></button>
              <button type="button" aria-label={t('Archive {name}', { name: sprint.name })} disabled={sprint.state === 'active'} onClick={remove}><Icon d={ARCHIVE} /></button>
              <button type="button" className="d" aria-label={t('Delete {name}', { name: sprint.name })} disabled={sprint.state === 'active'} onClick={remove}><Icon d={TRASH} /></button>
            </>
          )}
        </div>
        <div className="more">
          {sprint.state === 'planned' && (
            <>
              <button type="button" className="btn primary" disabled={start.isPending} onClick={() => start.mutate()}>{t('Start sprint')}</button>
              <button type="button" className="btn" onClick={() => setAdding((a) => !a)}>{t('Add tasks')}</button>
            </>
          )}
        </div>
      </div>
      {adding && <AddTasks projectId={projectId} sprint={sprint} onDone={() => { setAdding(false); onChange(); }} />}
    </>
  );
}

/** Manage sprints dialog (board.html): every open sprint with Edit / Archive / Delete, Start sprint and Add tasks. */
function ManageSprints({ projectId, projectName, items, onChange, onClose }: { projectId: string; projectName: string; items: Sprint[]; onChange: () => void; onClose: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  const add = useMutation({
    mutationFn: () => api(`/projects/${projectId}/sprints`, { method: 'POST', body: JSON.stringify({}) }),
    onSuccess: onChange,
    onError: (e) => toast.error(describeApiError(e, t('Could not add the sprint.'))),
  });
  const open = items.filter((s) => s.state !== 'completed');
  return (
    <dialog
      ref={ref}
      className="msd"
      aria-labelledby="msd-t"
      onClose={onClose}
      onClick={(e) => {
        if (e.target !== ref.current) return;
        const r = ref.current.getBoundingClientRect();
        if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) ref.current.close();
      }}
    >
      <div className="mh">
        <h3 id="msd-t">{t('Manage sprints')}</h3>
        <button type="button" className="btn primary" disabled={add.isPending} onClick={() => add.mutate()}>{t('+ Add sprint')}</button>
        <button type="button" className="x" aria-label={t('Close')} onClick={() => ref.current?.close()}>✕</button>
      </div>
      <p className="ms">{projectName} · {t('Plan and organize your sprints')}</p>
      <div className="table">
        <div className="sr th"><div>{t('Sprint')}</div><div>{t('Status')}</div><div>{t('Actions')}</div><div /></div>
        {open.map((s) => (
          <SprintRow key={`${s.id}-${s.version}`} projectId={projectId} sprint={s} onChange={onChange} />
        ))}
        {open.length === 0 && <div className="sr"><div>{t('No sprints yet.')}</div></div>}
      </div>
    </dialog>
  );
}

/** Board header (board.html): the active sprint, its dates, the Manage sprints burger and Complete sprint. Unfinished tasks go back to the backlog. */
export function SprintBar({ projectId, projectName = '' }: { projectId: string; projectName?: string }) {
  const { t } = usePrefs();
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [managing, setManaging] = useState(false);
  const sprints = useQuery({ queryKey: sprintKey(projectId), queryFn: () => api<{ items: Sprint[] }>(`/projects/${projectId}/sprints`), retry: false });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: sprintKey(projectId) });
    void qc.invalidateQueries({ queryKey: ['projects', projectId] });
    void qc.invalidateQueries({ queryKey: ['tasks'] });
  };
  const complete = useMutation({
    mutationFn: (s: Sprint) => api(`/projects/${projectId}/sprints/${s.id}/complete`, { method: 'POST', body: JSON.stringify({ version: s.version }) }),
    onSuccess: refresh,
    onError: (e) => toast.error(describeApiError(e, t('Could not complete the sprint.'))),
  });

  const items = sprints.data?.items ?? [];
  const active = items.find((s) => s.state === 'active');
  // No active sprint: show the next planned one, or an empty bar, so the board header keeps its place.
  const shown = active ?? items.find((s) => s.state === 'planned');
  const isPm = user?.role === 'pm';

  const confirmComplete = () => {
    if (active && window.confirm(t('Complete {name}? Unfinished tasks move back to the backlog.', { name: active.name }))) complete.mutate(active);
  };

  return (
    <div className="sprint-bar">
      <span className="sname">
        {shown?.name ?? t('No active sprint')}
        {shown && <span aria-hidden="true">⌄</span>}
      </span>
      {shown && <span className={shown.state === 'active' ? 'badge active' : 'badge'}>{t(shown.state === 'active' ? 'Active' : 'Planned')}</span>}
      {shown && <span className="dates">{formatDate(shown.start_date)} – {formatDate(shown.end_date)}</span>}
      {isPm && (
        <button type="button" className="burger" aria-label={t('Manage sprints')} onClick={() => setManaging(true)}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      )}
      {active && isPm && (
        <button type="button" className="btn primary" disabled={complete.isPending} onClick={confirmComplete}>
          {t('Complete sprint')}
        </button>
      )}
      {managing && <ManageSprints projectId={projectId} projectName={projectName} items={items} onChange={refresh} onClose={() => setManaging(false)} />}
    </div>
  );
}
