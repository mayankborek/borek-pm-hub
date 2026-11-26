import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { roadmapKey } from '@/features/milestones/milestonesApi';
import { formatDate, todayIso } from './projectUi';

/** Mirrors the fields of backend PhaseOut that the dialog uses. */
interface Phase {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  version: number;
}

const phasesKey = (projectId: string) => ['projects', 'phases', projectId] as const;

/** Backlog "Manage phases" (borek-flow-backlog2.html): list, add, edit, reorder and delete project phases. */
export function ManagePhases({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const qc = useQueryClient();
  const manage = useRef<HTMLDialogElement>(null);
  const formRef = useRef<HTMLDialogElement>(null);
  const confirmRef = useRef<HTMLDialogElement>(null);
  const [editing, setEditing] = useState<Phase | 'new' | null>(null);
  const [deleting, setDeleting] = useState<Phase | null>(null);
  const [form, setForm] = useState({ name: '', start_date: '', end_date: '' });
  const phases = useQuery({ queryKey: phasesKey(projectId), queryFn: () => api<Phase[]>(`/projects/${projectId}/phases`) });
  const items = phases.data ?? [];

  useEffect(() => {
    manage.current?.showModal();
  }, []);
  useEffect(() => {
    if (editing) formRef.current?.showModal();
    else formRef.current?.close();
  }, [editing]);
  useEffect(() => {
    if (deleting) confirmRef.current?.showModal();
    else confirmRef.current?.close();
  }, [deleting]);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: phasesKey(projectId) });
    void qc.invalidateQueries({ queryKey: roadmapKey(projectId) });
  };
  const fail = (fallback: string) => (e: unknown) => toast.error(describeApiError(e, t(fallback)));
  const save = useMutation({
    mutationFn: () => {
      const body = { name: form.name.trim(), start_date: form.start_date, end_date: form.end_date };
      return editing && editing !== 'new'
        ? api(`/projects/${projectId}/phases/${editing.id}`, { method: 'PATCH', body: JSON.stringify({ ...body, version: editing.version }) })
        : api(`/projects/${projectId}/phases`, { method: 'POST', body: JSON.stringify(body) });
    },
    onSuccess: () => {
      setEditing(null);
      refresh();
    },
    onError: fail('Could not save the phase.'),
  });
  const remove = useMutation({
    mutationFn: (p: Phase) => api(`/projects/${projectId}/phases/${p.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      setDeleting(null);
      refresh();
    },
    onError: (e) => {
      setDeleting(null);
      toast.error(describeApiError(e, t('Could not delete the phase.')));
    },
  });
  const reorder = useMutation({
    mutationFn: (ids: string[]) => api(`/projects/${projectId}/phases/order`, { method: 'PUT', body: JSON.stringify({ phase_ids: ids }) }),
    onSuccess: refresh,
    onError: fail('Could not reorder the phases.'),
  });
  const move = (i: number, dir: -1 | 1) => {
    const ids = items.map((p) => p.id);
    [ids[i], ids[i + dir]] = [ids[i + dir], ids[i]];
    reorder.mutate(ids);
  };
  const open = (p: Phase | 'new') => {
    setForm(p === 'new' ? { name: '', start_date: todayIso(), end_date: '' } : { name: p.name, start_date: p.start_date, end_date: p.end_date });
    setEditing(p);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <>
      <dialog ref={manage} className="bl-dialog manage" aria-labelledby="manage-title" onClose={onClose}>
        <div className="dhead">
          <h2 id="manage-title">{t('Manage phases')}</h2>
          <button type="button" className="dbtn solid" onClick={() => open('new')}>{t('+ Add phase')}</button>
          <button type="button" className="dbtn x" aria-label={t('Close')} onClick={() => manage.current?.close()}>×</button>
        </div>
        <p className="lead">{t('Phases organize the project timeline. Milestones remain linked to their tasks.')}</p>
        <div className="scroll">
          <table className="phases">
            <thead>
              <tr><th scope="col">{t('Phase')}</th><th scope="col">{t('Dates')}</th><th scope="col">{t('Actions')}</th></tr>
            </thead>
            <tbody>
              {items.map((p, i) => (
                <tr key={p.id}>
                  <th scope="row">{p.name}</th>
                  <td className="dates">{formatDate(p.start_date)}  –  {formatDate(p.end_date)}</td>
                  <td>
                    <div className="acts">
                      <button type="button" className="dbtn" aria-label={`${t('Edit')} ${p.name}`} onClick={() => open(p)}>{t('Edit')}</button>
                      <button type="button" className="dbtn" aria-label={`${t('Move up')} ${p.name}`} disabled={i === 0 || reorder.isPending} onClick={() => move(i, -1)}>↑</button>
                      <button type="button" className="dbtn" aria-label={`${t('Move down')} ${p.name}`} disabled={i === items.length - 1 || reorder.isPending} onClick={() => move(i, 1)}>↓</button>
                      <button type="button" className="dbtn" aria-label={`${t('Delete')} ${p.name}`} onClick={() => setDeleting(p)}>{t('Delete')}</button>
                    </div>
                  </td>
                </tr>
              ))}
              {!phases.isPending && items.length === 0 && (
                <tr><td colSpan={3} className="dates">{t('No phases yet.')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </dialog>

      <dialog ref={formRef} className="bl-dialog form" aria-labelledby="form-title" onClose={() => setEditing(null)}>
        <form onSubmit={submit}>
          <div className="dhead">
            <h2 id="form-title">{t(editing === 'new' ? 'Add phase' : 'Edit phase')}</h2>
            <button type="button" className="dbtn x" aria-label={t('Close')} onClick={() => setEditing(null)}>×</button>
          </div>
          <label>{t('Phase name')}<input required pattern=".*\S.*" autoComplete="off" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label>{t('Start date')}<input type="date" required value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></label>
          <label>{t('End date')}<input type="date" required min={form.start_date || undefined} value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></label>
          <p className="hint">{t('Milestones can be assigned to this phase or left without a phase.')}</p>
          <div className="actions">
            <button type="button" className="dbtn wide" onClick={() => setEditing(null)}>{t('Cancel')}</button>
            <button className="dbtn solid" disabled={save.isPending}>{t('Save phase')}</button>
          </div>
        </form>
      </dialog>

      <dialog ref={confirmRef} className="bl-dialog confirm" aria-labelledby="confirm-title" onClose={() => setDeleting(null)}>
        <h2 id="confirm-title">{t('Delete phase?')}</h2>
        <p>{t('The phase will be removed. Its milestones and tasks will be kept.')}</p>
        <div className="actions">
          <button type="button" className="dbtn wide" onClick={() => setDeleting(null)}>{t('Cancel')}</button>
          <button type="button" className="dbtn solid" disabled={remove.isPending} onClick={() => deleting && remove.mutate(deleting)}>{t('Delete phase')}</button>
        </div>
      </dialog>
    </>
  );
}
