import { useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { PagePlaceholder } from '@/shared/ui/PagePlaceholder';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { useProjects } from '@/features/projects/projectsApi';
import { TaskFilters, TaskGroup, TaskRow } from './TaskParts';
import { emptyFilter, useAllTasks, type TaskFilter } from './tasksApi';
import './tasks.css';

export const MyWorkPage = () => (
  <PagePlaceholder title="My Work" description="Tasks assigned to you across projects." />
);

/** Sidebar "Task List": GET /tasks across every project the user can access (backend scopes by role). */
export function TasksPage() {
  const [params, setParams] = useSearchParams();
  const projectId = params.get('project_id') ?? '';
  const [filter, setFilter] = useState<TaskFilter>(emptyFilter);
  const projects = useProjects();
  const { data, isPending, isError, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } = useAllTasks(projectId, filter);

  const tasks = useMemo(() => data?.pages.flatMap((p) => p.items) ?? [], [data]);
  const total = data?.pages[0]?.total ?? 0;
  const filtered = !!(filter.q.trim() || filter.category || filter.priority || filter.assigneeId || projectId);

  const projectFilter = (
    <select
      className="input"
      aria-label="Filter by project"
      value={projectId}
      onChange={(e) => setParams(e.target.value ? { project_id: e.target.value } : {})}
    >
      <option value="">Project: All</option>
      {projects.data?.items.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
  );

  return (
    <section className="page-body">
      <div className="page-header">
        <div>
          <p className="page-desc">All accessible projects</p>
          <h1 className="page-title">All project tasks</h1>
        </div>
      </div>

      <TaskFilters filter={filter} onChange={setFilter} tasks={tasks} extra={projectFilter} />

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
            {tasks.map((t) => (
              <TaskRow key={t.id} task={t} showProject />
            ))}
          </TaskGroup>
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

export function TaskDetailPage() {
  const { taskId } = useParams();
  return <PagePlaceholder title={`Task ${taskId}`} description="Task detail, status and assignee." />;
}
