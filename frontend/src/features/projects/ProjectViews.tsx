import { useMemo } from 'react';
import { PagePlaceholder } from '@/shared/ui/PagePlaceholder';
import { EmptyState, ErrorState, LoadingState } from '@/shared/ui/States';
import { TaskFilters, TaskGroup, TaskRow } from '@/features/tasks/TaskParts';
import { isFiltered, useUrlFilter } from '@/features/tasks/useUrlFilter';
import { useProjectTasks } from '@/features/tasks/tasksApi';
import { useProjectContext } from './ProjectLayout';

/** Backlog tab: GET /projects/{id}/tasks, planned work first, then tasks still in the Backlog category. */
export function ProjectListPage() {
  const project = useProjectContext();
  const { filter, applied, setFilter, clear } = useUrlFilter();
  const { data, isPending, isError, refetch } = useProjectTasks(project.id, applied);

  const { planned, backlog } = useMemo(() => {
    const items = data?.items ?? [];
    return {
      planned: items.filter((t) => t.status.category !== 'backlog'),
      backlog: items.filter((t) => t.status.category === 'backlog'),
    };
  }, [data]);

  if (isPending) return <LoadingState title="Loading tasks" text="Fetching this project’s tasks." />;
  if (isError) return <ErrorState title="We couldn’t load tasks" text="Check your connection and try again." onRetry={() => void refetch()} />;

  const filtered = isFiltered(applied);
  const noTasks = data.total === 0;

  return (
    <>
      <TaskFilters filter={filter} onChange={setFilter} onClear={clear} tasks={data.items} />
      {noTasks && !filtered ? (
        <EmptyState title="No tasks yet" text="Tasks added to this project will appear here." />
      ) : noTasks ? (
        <EmptyState title="No matching tasks" text="Try changing or clearing the filters." />
      ) : (
        <>
          <TaskGroup title="Board" count={planned.length} countLabel="project tasks" empty="No planned tasks yet.">
            {planned.map((t) => (
              <TaskRow key={t.id} task={t} />
            ))}
          </TaskGroup>
          <TaskGroup
            title="Backlog"
            count={backlog.length}
            empty="No backlog tasks yet. Tasks here stay off the Board until planned."
          >
            {backlog.map((t) => (
              <TaskRow key={t.id} task={t} />
            ))}
          </TaskGroup>
        </>
      )}
    </>
  );
}

export const ProjectMembersPage = () => (
  <PagePlaceholder title="Members" description="Project members and their roles." />
);
