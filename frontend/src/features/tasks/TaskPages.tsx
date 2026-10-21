import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PagePlaceholder } from '@/shared/ui/PagePlaceholder';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { TaskRow, TaskTableHead } from './TaskParts';
import { emptyFilter, useAllTasks } from './tasksApi';
import './tasks.css';

export const MyWorkPage = () => (
  <PagePlaceholder title="My Work" description="Tasks assigned to you across projects." />
);

/** Sidebar "Task List": GET /tasks across every project the user can access (backend scopes by role). */
export function TasksPage() {
  const [params] = useSearchParams();
  const projectId = params.get('project_id') ?? '';
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const { data, isPending, isError, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } = useAllTasks(projectId, emptyFilter);

  const tasks = useMemo(() => data?.pages.flatMap((p) => p.items) ?? [], [data]);
  const total = data?.pages[0]?.total ?? 0;
  const filtered = !!projectId;

  return (
    <section className="page-body">
      <div className="page-header">
        <div>
          <p className="page-crumb">Workspace / All accessible projects</p>
          <h1 className="page-title">All tasks</h1>
        </div>
        <button type="button" className="btn">
          Add Task
        </button>
      </div>

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
            <TaskTableHead />
            {tasks.map((t) => (
              <TaskRow
                key={t.id}
                task={t}
                showProject
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
