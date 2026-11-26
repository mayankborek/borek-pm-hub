import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useProjects } from '@/features/projects/projectsApi';
import { paths } from '@/app/routes';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { describeApiError } from '@/shared/api/client';
import { useToast } from '@/shared/ui/Toast';
import { TaskFilters, TaskGroup, TaskRow } from './TaskParts';
import { useAllTasks, useDeleteTask, useProjectStatuses } from './tasksApi';
import { EXPORT_FORMATS, exportFilter, exportTasks, type ExportFormat } from './jiraApi';
import { JiraImportDialog } from './JiraImportDialog';
import { isFiltered, useUrlFilter } from './useUrlFilter';
import './tasks.css';

const PER_PAGE = 10;

/** Sidebar "Task List": GET /tasks across every project the user can access (backend scopes by role). */
export function TasksPage() {
  const { t: tr } = usePrefs();
  const [params, setParams] = useSearchParams();
  const projects = useProjects().data?.items ?? [];
  const statuses = useProjectStatuses(params.get('project_id') ?? undefined).data;
  const { filter, applied, setFilter, clear } = useUrlFilter();
  const projectId = params.get('project_id') ?? '';
  const [page, setPage] = useState(1);
  const isPm = useAuth().user?.role === 'pm';
  const toast = useToast();
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportMenu, setExportMenu] = useState(false);
  const deleteTask = useDeleteTask();
  const { data, isPending, isError, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } = useAllTasks(projectId, applied);

  const loaded = useMemo(() => data?.pages.flatMap((p) => p.items) ?? [], [data]);
  const total = data?.pages[0]?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PER_PAGE));
  const current = Math.min(page, pages);
  const tasks = loaded.slice((current - 1) * PER_PAGE, current * PER_PAGE);
  const first = tasks.length ? (current - 1) * PER_PAGE + 1 : 0;

  // Pages are fetched on demand: keep loading until the requested page is covered.
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && loaded.length < current * PER_PAGE) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, loaded.length, current, fetchNextPage]);
  const filterKey = JSON.stringify(applied);
  useEffect(() => setPage(1), [projectId, filterKey]);
  const filtered = !!projectId || isFiltered(applied);

  const setProject = (id: string) =>
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (id) p.set('project_id', id);
        else p.delete('project_id');
        return p;
      },
      { replace: true },
    );
  const runExport = (format: ExportFormat) => {
    setExportMenu(false);
    setExporting(true);
    exportTasks({ project_id: projectId || undefined, filter: exportFilter(applied), format })
      .catch((e) => toast.error(describeApiError(e, tr('Could not export tasks.'))))
      .finally(() => setExporting(false));
  };

  return (
    <section className="page-body task-list-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">{tr('All project tasks')}</h1>
        </div>
        <div className="page-actions">
          {isPm && (
            <>
              <button type="button" className="btn secondary" onClick={() => setImporting(true)}>
                {tr('Import')}
              </button>
              <div className="export-menu">
                <button
                  type="button"
                  className="btn secondary"
                  aria-haspopup="menu"
                  aria-expanded={exportMenu}
                  disabled={exporting || total === 0}
                  onClick={() => setExportMenu((o) => !o)}
                  onKeyDown={(e) => e.key === 'Escape' && setExportMenu(false)}
                >
                  {tr(exporting ? 'Exporting…' : 'Export')} ▾
                </button>
                {exportMenu && (
                  <ul className="export-list" role="menu">
                    {EXPORT_FORMATS.map((f) => (
                      <li key={f} role="none">
                        <button type="button" role="menuitem" onClick={() => runExport(f)}>
                          {f.toUpperCase()}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
          <Link className="btn" to={projectId ? `${paths.taskNew}?project_id=${projectId}` : paths.taskNew}>
            {tr('Add Task')}
          </Link>
        </div>
      </div>
      {importing && <JiraImportDialog projects={projects} defaultProjectId={projectId} onClose={() => setImporting(false)} />}

      <TaskFilters
        filter={filter}
        onChange={setFilter}
        onClear={clear}
        tasks={tasks}
        combined
        statuses={statuses}
        extra={
          <select className="input" aria-label={tr('Filter by project')} value={projectId} onChange={(e) => setProject(e.target.value)}>
            <option value="">{tr('Project: All')}</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        }
      />

      {isPending ? (
        <LoadingState title="Loading tasks" text="Fetching tasks across your projects." />
      ) : isError ? (
        <ErrorState title="We couldn’t load tasks" text="Check your connection and try again." onRetry={() => void refetch()} />
      ) : total === 0 ? (
        <EmptyState
          title={filtered ? 'No matching tasks' : 'No tasks yet'}
          text={filtered ? 'Try changing or clearing the filters.' : 'Tasks from your projects will appear here.'}
        />
      ) : (
        <>
          <TaskGroup title="All tasks" count={total}>
            <div className={`task-row task-table-head${isPm ? ' has-actions' : ''}`} role="row">
              <div role="columnheader">{tr('Task / Project')}</div>
              <div role="columnheader">{tr('Status')}</div>
              <div role="columnheader">{tr('Due date')}</div>
              <div role="columnheader">{tr('Priority')}</div>
              <div role="columnheader">{tr('Assignee')}</div>
              {isPm && <div role="columnheader" />}
            </div>
            {tasks.map((t) => (
              <TaskRow
                key={t.id}
                task={t}
                showProject
                onDelete={
                  isPm
                    ? () => {
                        if (!window.confirm(tr('Delete {key} · {title}?', { key: t.key, title: t.title }))) return;
                        deleteTask.mutate(t.id, {
                          onSuccess: () => toast.success(tr('{key} deleted.', { key: t.key })),
                          onError: (e) => toast.error(describeApiError(e, tr('Could not delete the task.'))),
                        });
                      }
                    : undefined
                }
              />
            ))}
          </TaskGroup>
          <div className="task-foot task-pager">
            <span>{tr('Showing {from}–{to} of {total} tasks · {n} per page', { from: first, to: first + tasks.length - 1, total, n: PER_PAGE })}</span>
            <nav aria-label={tr('Pagination')}>
              <span>{tr('Page {n} of {total}', { n: current, total: pages })}</span>
              <button type="button" aria-label={tr('Previous page')} disabled={current === 1} onClick={() => setPage(current - 1)}>‹</button>
              {Array.from({ length: pages }, (_, i) => i + 1)
                .filter((n) => pages <= 7 || n === 1 || n === pages || Math.abs(n - current) <= 1)
                .map((n, i, all) => (
                  <span key={n} className="pager-item">
                    {i > 0 && n - all[i - 1] > 1 && <span className="pager-gap">…</span>}
                    <button type="button" aria-current={n === current ? 'page' : undefined} className={n === current ? 'on' : undefined} onClick={() => setPage(n)}>{n}</button>
                  </span>
                ))}
              <button type="button" aria-label={tr('Next page')} disabled={current === pages} onClick={() => setPage(current + 1)}>›</button>
            </nav>
          </div>
        </>
      )}
    </section>
  );
}
