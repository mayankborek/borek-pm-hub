import { useEffect, useState } from 'react';
import { emptyFilter, useAllTasks, type Task, type TaskDetail } from './tasksApi';

export type Relationship = 'related' | 'blocks' | 'blocked_by' | 'duplicates';

export const relationLabels: Record<Relationship, string> = {
  related: 'Related to',
  blocks: 'Blocks',
  blocked_by: 'Blocked by',
  duplicates: 'Duplicates',
};

interface Props {
  task: TaskDetail;
  onClose: () => void;
  onAdd: (relation: Relationship, other: Task) => void;
}

/** Right-hand drawer from Figma "PM · Related Task drawer · Search": pick a relationship, search a task, add it. */
export function RelatedTaskDrawer({ task, onClose, onAdd }: Props) {
  const [relation, setRelation] = useState<Relationship>('related');
  const [q, setQ] = useState('');
  const [picked, setPicked] = useState<Task | null>(null);
  const query = q.trim();
  const results = useAllTasks('', { ...emptyFilter, q: query });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const matches = query ? (results.data?.pages.flatMap((p) => p.items) ?? []).filter((t) => t.id !== task.id) : [];

  return (
    <div className="rd-overlay">
      <button type="button" className="rd-dismiss" aria-label="Dismiss drawer" onClick={onClose} />
      <aside className="rd-drawer" role="dialog" aria-modal="true" aria-labelledby="rd-title">
        <div className="rd-content">
          <div className="rd-head">
            <h2 id="rd-title">Related Task</h2>
            <button type="button" className="td-outline rd-close" onClick={onClose}>
              Close
            </button>
          </div>
          <p className="td-sub">
            {task.key} · {task.title}
          </p>
          <hr className="rd-rule" />
          <div className="rd-field">
            <label htmlFor="rd-relation">Relationship</label>
            <select id="rd-relation" value={relation} onChange={(e) => setRelation(e.target.value as Relationship)}>
              {(Object.keys(relationLabels) as Relationship[]).map((r) => (
                <option key={r} value={r}>
                  {relationLabels[r]}
                </option>
              ))}
            </select>
          </div>
          <div className="rd-field">
            <label htmlFor="rd-search">Task</label>
            <input
              id="rd-search"
              type="search"
              autoFocus
              placeholder="Search by task ID or title…"
              value={picked ? `${picked.key} · ${picked.title}` : q}
              onChange={(e) => {
                setPicked(null);
                setQ(e.target.value);
              }}
            />
            {!picked && query && (
              <ul className="rd-results" role="listbox" aria-label="Matching tasks">
                {results.isPending && <li className="rd-note">Searching…</li>}
                {!results.isPending && matches.length === 0 && <li className="rd-note">No matching tasks.</li>}
                {matches.map((t) => (
                  <li key={t.id} role="option" aria-selected={false} tabIndex={0} onClick={() => setPicked(t)}
                    onKeyDown={(e) => e.key === 'Enter' && setPicked(t)}>
                    <strong>{t.key}</strong> · {t.title}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <div className="rd-footer">
          <button type="button" className="td-outline rd-btn" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn rd-btn" disabled={!picked} onClick={() => picked && onAdd(relation, picked)}>
            Add related task
          </button>
        </div>
      </aside>
    </div>
  );
}
