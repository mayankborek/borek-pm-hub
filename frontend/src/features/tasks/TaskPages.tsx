import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useAuth } from '@/features/auth/AuthContext';
import { describeApiError } from '@/shared/api/client';
import { useToast } from '@/shared/ui/Toast';
import { TaskRow, TaskTableHead } from './TaskParts';
import { TaskFilters } from './TaskParts';
import { useAllTasks, useDeleteTask } from './tasksApi';
import { isFiltered, useUrlFilter } from './useUrlFilter';
import './tasks.css';

/** Sidebar "Task List": GET /tasks across every project the user can access (backend scopes by role). */
export function TasksPage() {
  const [params] = useSearchParams();
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

  return (
    <section className="page-body">
      <div className="page-header">
        <div>
          <p className="page-crumb">Workspace / All accessible projects</p>
          <h1 className="page-title">All tasks</h1>
        </div>
        <Link className="btn" to={projectId ? `${paths.taskNew}?project_id=${projectId}` : paths.taskNew}>
          Add Task
        </Link>
      </div>

      <TaskFilters filter={filter} onChange={setFilter} onClear={clear} tasks={tasks} />

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
          <section className="task-group table" role="table" aria-label="All tasks">
            <TaskTableHead withActions={isPm} />
            {tasks.map((t) => (
              <TaskRow
                key={t.id}
                task={t}
                showProject
                onDelete={
                  isPm
                    ? () => {
                        if (!window.confirm(`Delete ${t.key} · ${t.title}?`)) return;
                        deleteTask.mutate(t.id, {
                          onSuccess: () => {
                            setSelected((prev) => {
                              const next = new Set(prev);
                              next.delete(t.id);
                              return next;
                            });
                            toast.success(`${t.key} deleted.`);
                          },
                          onError: (e) => toast.error(describeApiError(e, 'Could not delete the task.')),
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
          </section>
          <p className="task-foot">
            Showing {tasks.length} of {total} tasks
            {hasNextPage && (
              <>
                {' · '}
                <button type="button" disabled={isFetchingNextPage} onClick={() => void fetchNextPage()}>
                  {isFetchingNextPage ? 'Loading…' : 'Load more'}
                </button>
              </>
            )}
          </p>
        </>
      )}
    </section>
  );
}
