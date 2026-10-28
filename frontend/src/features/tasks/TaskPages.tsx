import { useMemo, useState } from 'react';
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
import { isFiltered, useUrlFilter } from './useUrlFilter';
import './tasks.css';

/** Sidebar "Task List": GET /tasks across every project the user can access (backend scopes by role). */
export function TasksPage() {
  const { t: tr } = usePrefs();
  const [params, setParams] = useSearchParams();
  const projects = useProjects().data?.items ?? [];
  const statuses = useProjectStatuses(params.get('project_id') ?? undefined).data;
  const { filter, applied, setFilter, clear } = useUrlFilter();
  const projectId = params.get('project_id') ?? '';
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const isPm = useAuth().user?.role === 'pm';
  const toast = useToast();
  const deleteTask = useDeleteTask();
  const { data, isPending, isError, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } = useAllTasks(projectId, applied);

  const tasks = useMemo(() => data?.pages.flatMap((p) => p.items) ?? [], [data]);
  const total = data?.pages[0]?.total ?? 0;
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
  const allSelected = tasks.length > 0 && tasks.every((t) => selected.has(t.id));

  return (
    <section className="page-body task-list-page">
      <div className="page-header">
        <div>
          <p className="page-crumb">{tr('All accessible projects')}</p>
          <h1 className="page-title">{tr('All project tasks')}</h1>
        </div>
        <Link className="btn" to={projectId ? `${paths.taskNew}?project_id=${projectId}` : paths.taskNew}>
          {tr('Add Task')}
        </Link>
      </div>

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
          <TaskGroup
            title="All tasks"
            count={total}
            selectAll={{
              checked: allSelected,
              indeterminate: !allSelected && selected.size > 0,
              onChange: (on) => setSelected(on ? new Set(tasks.map((t) => t.id)) : new Set()),
            }}
          >
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
                          onSuccess: () => {
                            setSelected((prev) => {
                              const next = new Set(prev);
                              next.delete(t.id);
                              return next;
                            });
                            toast.success(tr('{key} deleted.', { key: t.key }));
                          },
                          onError: (e) => toast.error(describeApiError(e, tr('Could not delete the task.'))),
                        });
                      }
                    : undefined
                }
                selected={selected.has(t.id)}
                onSelect={(on) =>
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (on) next.add(t.id);
                    else next.delete(t.id);
                    return next;
                  })
                }
              />
            ))}
          </TaskGroup>
          <p className="task-foot">
            {tr('Showing {n} of {total} tasks', { n: tasks.length, total })}
            {hasNextPage && (
              <>
                {' · '}
                <button type="button" disabled={isFetchingNextPage} onClick={() => void fetchNextPage()}>
                  {tr(isFetchingNextPage ? 'Loading…' : 'Load more')}
                </button>
              </>
            )}
          </p>
        </>
      )}
    </section>
  );
}
