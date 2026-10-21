import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { emptyFilter, type TaskFilter } from './tasksApi';

const KEYS = { q: 'q', category: 'status', priority: 'priority', assigneeId: 'person' } as const;
const DEBOUNCE_MS = 250;

export const isFiltered = (f: TaskFilter) => !!(f.q.trim() || f.category || f.priority || f.assigneeId);

/**
 * Task filter state held in the URL, so refresh, back and shared links keep it.
 * `filter` follows the inputs; `applied` is the debounced value to query with.
 * Unrelated params (e.g. project_id) are preserved on every change.
 */
export function useUrlFilter() {
  const [params, setParams] = useSearchParams();

  const filter = useMemo<TaskFilter>(
    () => ({
      q: params.get(KEYS.q) ?? '',
      category: (params.get(KEYS.category) ?? '') as TaskFilter['category'],
      priority: (params.get(KEYS.priority) ?? '') as TaskFilter['priority'],
      assigneeId: params.get(KEYS.assigneeId) ?? '',
    }),
    [params],
  );

  const setFilter = useCallback(
    (next: TaskFilter) =>
      setParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          (Object.keys(KEYS) as (keyof TaskFilter)[]).forEach((k) => {
            if (next[k]) p.set(KEYS[k], next[k]);
            else p.delete(KEYS[k]);
          });
          return p;
        },
        { replace: true },
      ),
    [setParams],
  );

  const clear = useCallback(() => setFilter(emptyFilter), [setFilter]);

  const [applied, setApplied] = useState(filter);
  useEffect(() => {
    if (filter.q === applied.q) return setApplied(filter);
    const id = setTimeout(() => setApplied(filter), DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [filter, applied.q]);

  return { filter, applied, setFilter, clear };
}
