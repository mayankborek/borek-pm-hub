import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { usePopover } from '@/features/admin/AdminUi';
import { emptyFilter, type StatusCategory, type TaskFilter, type TaskPriority, type TaskStatusOption } from '@/features/tasks/tasksApi';
import { PRIORITY_COLOR, PRIORITY_LABEL, STATUS_COLOR, priorityPath } from '@/features/accountManager/amWork';

/** Status text colour from borek-flow-screens: named workflow states keep their colour, others follow their category. */
const CATEGORY_COLOR: Record<StatusCategory, string> = { backlog: '#5C6178', todo: '#5C6178', in_progress: '#175DBA', blocked: '#AD1F1F', done: '#17735E' };
export const statusTone = (name: string, category?: StatusCategory) => STATUS_COLOR[name] ?? (category ? CATEGORY_COLOR[category] : '#5C6178');

const AVATARS: [string, string][] = [
  ['#D9D2F3', '#3F2A8C'],
  ['#F9DCD6', '#9C2B1F'],
  ['#FFF1D0', '#8A5A00'],
  ['#DCE8FA', '#154F91'],
  ['#E0F5E8', '#17735E'],
];
const initialsOf = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('');

/** A stable colour per person, so the same name always gets the same avatar. */
export function Avatar({ name, size = 24, solid }: { name: string; size?: number; solid?: boolean }) {
  const [bg, ink] = AVATARS[[...name].reduce((n, c) => n + c.charCodeAt(0), 0) % AVATARS.length];
  return (
    <span className="dv-av" style={{ width: size, height: size, fontSize: size > 28 ? 11 : 8, background: solid ? '#154F91' : bg, color: solid ? '#fff' : ink }} aria-hidden="true">
      {initialsOf(name)}
    </span>
  );
}

export function PriorityMark({ priority, label = true }: { priority: TaskPriority; label?: boolean }) {
  const { t } = usePrefs();
  return (
    <span className="dv-pri" style={{ color: PRIORITY_COLOR[priority] }} title={t(PRIORITY_LABEL[priority])}>
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={priorityPath(priority)} />
      </svg>
      {label ? <span className="dv-pri-t">{t(PRIORITY_LABEL[priority])}</span> : <span className="sr-only">{t(PRIORITY_LABEL[priority])}</span>}
    </span>
  );
}

export const Chevron = ({ size = 10 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M2.5 4.5 6 8l3.5-3.5" />
  </svg>
);

export const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
    <circle cx="7" cy="7" r="4.5" />
    <path d="m10.5 10.5 3 3" />
  </svg>
);

/** Plain-text date as the design writes it: 18 Oct 2026 (long) or 18 Oct (short). */
export function fmtDate(iso: string | null | undefined, long = true): string {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-').map(Number);
  const text = new Date(y, m - 1, d).toLocaleDateString(document.documentElement.lang === 'de' ? 'de-DE' : 'en-GB', { day: '2-digit', month: 'short', ...(long ? { year: 'numeric' } : {}) });
  return text;
}

/** Task filters held in the URL. The assignee defaults to the signed-in developer (`person=all` shows everyone). */
export function useDevFilter() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const person = params.get('person');
  const [q, setQ] = useState(params.get('q') ?? '');
  const [applied, setApplied] = useState(q);
  useEffect(() => {
    const id = setTimeout(() => setApplied(q), 250);
    return () => clearTimeout(id);
  }, [q]);

  const set = useCallback(
    (key: string, value: string) =>
      setParams((prev) => {
        const p = new URLSearchParams(prev);
        if (value) p.set(key, value);
        else p.delete(key);
        return p;
      }, { replace: true }),
    [setParams],
  );

  const filter: TaskFilter = useMemo(
    () => ({
      ...emptyFilter,
      q: applied,
      statusId: params.get('status_id') ?? '',
      priority: (params.get('priority') ?? '') as TaskPriority | '',
      assigneeId: person === 'all' ? '' : (person ?? user?.id ?? ''),
    }),
    [applied, params, person, user?.id],
  );
  return {
    filter,
    q,
    setQ,
    mine: person !== 'all',
    setMine: (on: boolean) => set('person', on ? '' : 'all'),
    setStatus: (v: string) => set('status_id', v),
    setPriority: (v: string) => set('priority', v),
    active: !!(filter.statusId || filter.priority),
    clear: () => setParams(new URLSearchParams(), { replace: true }),
  };
}

type DevFilter = ReturnType<typeof useDevFilter>;

/** Search box, the signed-in person chip and the Filter menu (status and priority). */
export function FilterBar({ f, statuses }: { f: DevFilter; statuses: TaskStatusOption[] }) {
  const { t } = usePrefs();
  const { user } = useAuth();
  const menu = usePopover();
  return (
    <div className="dv-filters">
      <label className="dv-search">
        <SearchIcon />
        <input type="search" value={f.q} placeholder={t('Search tasks ...')} aria-label={t('Search tasks')} onChange={(e) => f.setQ(e.target.value)} />
      </label>
      {user && (
        f.mine ? (
          <span className="dv-chip">
            <Avatar name={user.name} size={24} solid />
            {user.name}
            <button type="button" aria-label={t('Show everyone’s tasks')} onClick={() => f.setMine(false)}>×</button>
          </span>
        ) : (
          <button type="button" className="dv-fbtn" onClick={() => f.setMine(true)}>{t('Only my tasks')}</button>
        )
      )}
      <div className="dv-anchor" ref={menu.ref}>
        <button type="button" className={f.active ? 'dv-fbtn on' : 'dv-fbtn'} aria-haspopup="true" aria-expanded={menu.open} onClick={() => menu.setOpen((o) => !o)}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true"><path d="M1 2h2v2H1zM5 2h6v2H5zM1 7h2v2H1zM5 7h6v2H5z" /></svg>
          {t('Filter')}
        </button>
        {menu.open && (
          <div className="dv-pop dv-fmenu">
            <label>
              {t('Status')}
              <select value={f.filter.statusId} onChange={(e) => f.setStatus(e.target.value)}>
                <option value="">{t('All statuses')}</option>
                {statuses.map((s) => <option key={s.id} value={s.id}>{t(s.name)}</option>)}
              </select>
            </label>
            <label>
              {t('Priority')}
              <select value={f.filter.priority} onChange={(e) => f.setPriority(e.target.value)}>
                <option value="">{t('All priorities')}</option>
                {(['highest', 'high', 'medium', 'low', 'lowest'] as const).map((p) => <option key={p} value={p}>{t(PRIORITY_LABEL[p])}</option>)}
              </select>
            </label>
            {f.active && <button type="button" className="dv-link" onClick={f.clear}>{t('Clear filters')}</button>}
          </div>
        )}
      </div>
    </div>
  );
}

/** A value that opens a list of options (task Properties). The chevron sits at the row's right edge. */
export function Dropdown<T extends string>({ value, options, label, onChange, color }: {
  value: T;
  options: { value: T; label: ReactNode; text: string }[];
  label: string;
  onChange: (v: T) => void;
  color?: string;
}) {
  const pop = usePopover();
  const current = options.find((o) => o.value === value);
  return (
    <div className="dv-dd" ref={pop.ref}>
      <button type="button" aria-haspopup="listbox" aria-expanded={pop.open} aria-label={`${label}: ${current?.text ?? ''}`} style={color ? { color } : undefined} onClick={() => pop.setOpen((o) => !o)}>
        <span>{current?.label ?? '—'}</span>
        <Chevron size={9} />
      </button>
      {pop.open && (
        <ul className="dv-pop dv-dd-list" role="listbox" aria-label={label}>
          {options.map((o) => (
            <li key={o.value}>
              <button type="button" role="option" aria-selected={o.value === value} onClick={() => { pop.setOpen(false); if (o.value !== value) onChange(o.value); }}>{o.label}</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Pages of ten with the "Showing 1–10 of 25 tasks · 10 per page" line from the Backlog design. */
export function Pager({ page, total, size, noun = 'tasks', onPage }: { page: number; total: number; size: number; noun?: string; onPage: (p: number) => void }) {
  const { t } = usePrefs();
  const pages = Math.max(1, Math.ceil(total / size));
  const from = total === 0 ? 0 : (page - 1) * size + 1;
  const to = Math.min(total, page * size);
  return (
    <div className="dv-pager">
      <span>{total === 0 ? t('{n} tasks · {size} per page', { n: 0, size }) : t('Showing {from}–{to} of {total} {noun} · {size} per page', { from, to, total, noun: t(noun), size })}</span>
      <nav aria-label={t('Pages')}>
        <button type="button" aria-label={t('Previous page')} disabled={page <= 1} onClick={() => onPage(page - 1)}>‹</button>
        {Array.from({ length: pages }, (_, i) => i + 1).map((n) => (
          <button key={n} type="button" className={n === page ? 'on' : undefined} aria-current={n === page ? 'page' : undefined} onClick={() => onPage(n)}>{n}</button>
        ))}
        <button type="button" aria-label={t('Next page')} disabled={page >= pages} onClick={() => onPage(page + 1)}>›</button>
      </nav>
    </div>
  );
}

/** Closes `onClose` on Escape; used by inline composers. */
export function useEscape(onClose: () => void) {
  const ref = useRef(onClose);
  ref.current = onClose;
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && ref.current();
    document.addEventListener('keydown', k);
    return () => document.removeEventListener('keydown', k);
  }, []);
}
