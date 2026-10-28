import { useMemo, useState } from 'react';
import { PagePlaceholder } from '@/shared/ui/PagePlaceholder';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { QuickCreateTask } from '@/features/tasks/QuickCreateTask';
import { TaskFilters, TaskGroup, TaskRow } from '@/features/tasks/TaskParts';
import { isFiltered, useUrlFilter } from '@/features/tasks/useUrlFilter';
import { useProjectStatuses, useProjectTasks } from '@/features/tasks/tasksApi';
import { useProjectContext } from './ProjectLayout';

/** Backlog tab: GET /projects/{id}/tasks, only tasks in the Backlog category; new tasks land here by default. */
export function ProjectListPage() {
  const project = useProjectContext();
  const [creating, setCreating] = useState(false);
  const { filter, applied, setFilter, clear } = useUrlFilter();
  const { data: statuses } = useProjectStatuses(project.id);
  const { data, isPending, isError, refetch } = useProjectTasks(project.id, applied);

  const backlog = useMemo(() => (data?.items ?? []).filter((t) => t.status.category === 'backlog'), [data]);

  if (isPending) return <LoadingState title="Loading tasks" text="Fetching this project’s tasks." />;
  if (isError) return <ErrorState title="We couldn’t load tasks" text="Check your connection and try again." onRetry={() => void refetch()} />;

  const filtered = isFiltered(applied);

  return (
    <>
      <TaskFilters filter={filter} onChange={setFilter} onClear={clear} tasks={data.items} combined statuses={statuses} />
      <TaskGroup
        title="Backlog"
        count={backlog.length}
        empty={filtered ? 'No matching backlog tasks. Try changing or clearing the filters.' : 'No backlog tasks yet. New tasks land here and stay off the Board until planned.'}
        action={
          <button type="button" className="btn" onClick={() => setCreating(true)}>
            Add task
          </button>
        }
      >
        {backlog.map((t) => (
          <TaskRow key={t.id} task={t} />
        ))}
      </TaskGroup>
      {creating && <QuickCreateTask projectId={project.id} statuses={statuses} onClose={() => setCreating(false)} />}
    </>
  );
}

export const ProjectMembersPage = () => (
  <PagePlaceholder title="Members" description="Project members and their roles." />
);
