import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useClientPortal } from '@/features/client/clientPortalApi';
import { paddedDate } from '@/features/client/format';
import { PortalPending } from '@/features/client/ui';
import type { WorkPriority } from '@/features/client/types';
import { PRIORITIES, PRIORITY_LABEL, avatarColor, initialsOf, statusNames } from './amWork';
import { Person, PriorityMark, StatusText } from './AmWorkParts';
import './amWork.css';

const PAGE = 10;

/** Task List (design2): every task of the client's projects, with search, project, assignee and filter. */
export function AmTasksPage() {
  const { t, lang } = usePrefs();
  const query = useClientPortal();
  const { data } = query;
  const [q, setQ] = useState('');
  const [projectId, setProjectId] = useState('');
  const [people, setPeople] = useState<string[]>([]);
  const [showFilter, setShowFilter] = useState(false);
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState<WorkPriority | ''>('');
  const [page, setPage] = useState(1);

  const all = useMemo(
    () => (data?.projects ?? []).flatMap((p) => (p.workItems ?? []).map((w) => ({ ...w, project: p.name, projectId: p.id }))),
    [data],
  );
  const names = useMemo(() => [...new Set(all.map((w) => w.assignee).filter((n): n is string => !!n))].sort(), [all]);
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return all.filter(
      (w) =>
        (!projectId || w.projectId === projectId) &&
        (!people.length || (w.assignee !== null && people.includes(w.assignee))) &&
        (!status || w.status === status) &&
        (!priority || w.priority === priority) &&
        (!needle || `${w.ref} ${w.title} ${w.project}`.toLowerCase().includes(needle)),
    );
  }, [all, q, projectId, people, status, priority]);

  if (!data) return <PortalPending query={query} />;

  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const current = Math.min(page, pages);
  const shown = rows.slice((current - 1) * PAGE, current * PAGE);
  /** A filter change returns to the first page. */
  const filtered = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };
  const toggle = (n: string) => filtered(setPeople)(people.includes(n) ? people.filter((x) => x !== n) : [...people, n]);

  return (
    <div className="am-page wk">
      <h1>{t('All project tasks')}</h1>
      <div className="wk-bar">
        <input type="search" value={q} onChange={(e) => filtered(setQ)(e.target.value)} placeholder={t('Search tasks ...')} aria-label={t('Search tasks')} />
        <select value={projectId} onChange={(e) => filtered(setProjectId)(e.target.value)} aria-label={t('Project')}>
          <option value="">{t('Project: All')}</option>
          {data.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <span className="wk-people" role="group" aria-label={t('Assignee')}>
          {names.map((n) => (
            <button key={n} type="button" className={people.includes(n) ? 'on' : undefined} aria-pressed={people.includes(n)} title={n} onClick={() => toggle(n)} style={{ background: avatarColor(n) }}>
              {initialsOf(n)}
            </button>
          ))}
        </span>
        <button type="button" className="wk-filter" aria-expanded={showFilter} onClick={() => setShowFilter((v) => !v)}>{t('Filter')}</button>
      </div>
      {showFilter && (
        <div className="wk-bar wk-extra">
          <select value={status} onChange={(e) => filtered(setStatus)(e.target.value)} aria-label={t('Status')}>
            <option value="">{t('Status: All')}</option>
            {statusNames(all).map((s) => <option key={s} value={s}>{t(s)}</option>)}
          </select>
          <select value={priority} onChange={(e) => filtered(setPriority)(e.target.value as WorkPriority | '')} aria-label={t('Priority')}>
            <option value="">{t('Priority: All')}</option>
            {PRIORITIES.map((p) => <option key={p} value={p}>{t(PRIORITY_LABEL[p])}</option>)}
          </select>
        </div>
      )}

      <section className="card wk-card">
        <h3>{t('All tasks')} <small>{t('{n} tasks', { n: rows.length })}</small></h3>
        {shown.length === 0 ? (
          <p className="small wk-empty">{t('No tasks match these filters.')}</p>
        ) : (
          <table className="wk-table">
            <thead>
              <tr><th>{t('Task / Project')}</th><th>{t('Status')}</th><th>{t('Due date')}</th><th>{t('Priority')}</th><th>{t('Assignee')}</th></tr>
            </thead>
            <tbody>
              {shown.map((w) => (
                <tr key={w.id}>
                  <td><Link to={paths.amBoard(w.projectId)} className="wk-title">{w.ref} · {w.title} · {w.project}</Link></td>
                  <td><StatusText status={w.status} /></td>
                  <td className="muted">{w.dueDate ? paddedDate(lang, w.dueDate) : '–'}</td>
                  <td><PriorityMark priority={w.priority} /></td>
                  <td><Person name={w.assignee} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <footer className="wk-foot">
          <span>{t('Showing {a}–{b} of {n} tasks · {p} per page', { a: rows.length ? (current - 1) * PAGE + 1 : 0, b: Math.min(current * PAGE, rows.length), n: rows.length, p: PAGE })}</span>
          <nav aria-label={t('Pages')}>
            <span>{t('Page {a} of {b}', { a: current, b: pages })}</span>
            <button type="button" disabled={current <= 1} onClick={() => setPage(current - 1)} aria-label={t('Previous page')}>‹</button>
            {Array.from({ length: pages }, (_, i) => i + 1).map((n) => (
              <button key={n} type="button" className={n === current ? 'on' : undefined} aria-current={n === current ? 'page' : undefined} onClick={() => setPage(n)}>{n}</button>
            ))}
            <button type="button" disabled={current >= pages} onClick={() => setPage(current + 1)} aria-label={t('Next page')}>›</button>
          </nav>
        </footer>
      </section>
    </div>
  );
}
