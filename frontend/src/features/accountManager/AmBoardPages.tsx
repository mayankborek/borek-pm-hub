import { useMemo, useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useProjectContext } from '@/features/client/ClientProjectLayout';
import { paddedDate, shortDate } from '@/features/client/format';
import { EmptyCard } from '@/features/client/ui';
import { CR_LABEL } from '@/features/client/labels';
import { statusColor, statusNames } from './amWork';
import { Person, PriorityMark, StatusText } from './AmWorkParts';
import './amWork.css';

/** Open tasks of the current project that match the search box. */
function useOpenTasks() {
  const { t } = usePrefs();
  const { project } = useProjectContext();
  const [q, setQ] = useState('');
  const needle = q.trim().toLowerCase();
  const open = useMemo(
    () => (project.workItems ?? []).filter((w) => !w.done && `${w.ref} ${w.title}`.toLowerCase().includes(needle)),
    [project, needle],
  );
  const search = (
    <div className="wk-bar">
      <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('Search tasks ...')} aria-label={t('Search tasks')} />
    </div>
  );
  return { open, search };
}

/** Backlog tab: the project's open tasks as a list. */
export function AmBacklogPage() {
  const { t, lang } = usePrefs();
  const { open, search } = useOpenTasks();
  return (
    <div className="wk">
      {search}
      <section className="card wk-card">
        <h3>{t('Backlog')} <small>{t('{n} tasks', { n: open.length })}</small></h3>
        {open.length === 0 ? (
          <p className="small wk-empty">{t('No open tasks.')}</p>
        ) : (
          <table className="wk-table">
            <thead><tr><th>{t('Task')}</th><th>{t('Status')}</th><th>{t('Due date')}</th><th>{t('Priority')}</th><th>{t('Assignee')}</th></tr></thead>
            <tbody>
              {open.map((w) => (
                <tr key={w.id}>
                  <td className="wk-title">{w.ref} · {w.title}</td>
                  <td><StatusText status={w.status} /></td>
                  <td className="muted">{w.dueDate ? paddedDate(lang, w.dueDate) : '–'}</td>
                  <td><PriorityMark priority={w.priority} /></td>
                  <td><Person name={w.assignee} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

/** Board tab: open tasks in one column per status (read-only for Account Managers). */
export function AmBoardPage() {
  const { t, lang } = usePrefs();
  const { open, search } = useOpenTasks();
  const columns = statusNames(open);
  return (
    <div className="wk">
      {search}
      {columns.length === 0 ? (
        <EmptyCard title="No open tasks" text="Open tasks of this project appear here, one column per status." />
      ) : (
        <div className="wk-board">
          {columns.map((s) => (
            <section key={s} className="wk-col" aria-label={t(s)}>
              <h4 style={{ color: statusColor(s) }}>{t(s)}</h4>
              {open.filter((w) => w.status === s).map((w) => (
                <article key={w.id} className="wk-cardt">
                  <header>
                    <span className="wk-chip"><i style={{ background: statusColor(w.status) }} />{t(w.status)}</span>
                    <PriorityMark priority={w.priority} label={false} />
                  </header>
                  <b>{w.title}</b>
                  <footer>
                    <Person name={w.assignee} label={false} />
                    <span>{w.dueDate ? t('Due {date}', { date: shortDate(lang, w.dueDate) }) : ''}</span>
                  </footer>
                </article>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

/** Change Requests tab: the project's requests and where each stands. */
export function AmChangeRequestsPage() {
  const { project } = useProjectContext();
  const { t } = usePrefs();
  const rows = project.changeRequests;
  return (
    <div className="wk">
      <section className="card wk-card">
        <h3>{t('Change Requests')} <small>{t('{n} requests in total', { n: rows.length })}</small></h3>
        {rows.length === 0 ? (
          <p className="small wk-empty">{t('No change requests yet.')}</p>
        ) : (
          <table className="wk-table">
            <thead><tr><th>{t('Request')}</th><th>{t('Status')}</th></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.ref}><td className="wk-title">{c.ref} · {c.title}</td><td>{t(CR_LABEL[c.status])}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
