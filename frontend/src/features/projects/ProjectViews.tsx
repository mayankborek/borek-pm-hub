import { useMemo, useState } from 'react';
import { PagePlaceholder } from '@/shared/ui/PagePlaceholder';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { QuickCreateTask } from '@/features/tasks/QuickCreateTask';
import { TaskFilters, TaskGroup, TaskRow } from '@/features/tasks/TaskParts';
import { isFiltered, useUrlFilter } from '@/features/tasks/useUrlFilter';
import { useMoveTask, useProjectStatuses, useProjectTasks, type Task } from '@/features/tasks/tasksApi';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { useProjectContext } from './ProjectLayout';

const BOARD_PAGE = 6;

/** Backlog tab: GET /projects/{id}/tasks, a Board group (planned work) above the Backlog group; new tasks land in Backlog by default. */
export function ProjectListPage() {
  const project = useProjectContext();
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [boardSelected, setBoardSelected] = useState<Set<string>>(new Set());
  const [boardShown, setBoardShown] = useState(BOARD_PAGE);
  const { filter, applied, setFilter, clear } = useUrlFilter();
  const { data: statuses } = useProjectStatuses(project.id);
  const { data, isPending, isError, refetch } = useProjectTasks(project.id, applied);

  const backlog = useMemo(() => (data?.items ?? []).filter((t) => t.status.category === 'backlog'), [data]);
  const board = useMemo(() => (data?.items ?? []).filter((t) => t.status.category !== 'backlog'), [data]);
  const { t: tr } = usePrefs();
  const toast = useToast();
  const moveTask = useMoveTask();

  // A planned task starts in the first "To do" status, else the first non-Backlog status on the Board.
  const boardStatuses = [...(statuses ?? [])].filter((s) => s.category !== 'backlog').sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
  const target = boardStatuses.find((s) => s.category === 'todo') ?? boardStatuses[0];

  const backlogStatus = [...(statuses ?? [])].filter((s) => s.category === 'backlog').sort((a, b) => (a.position ?? 0) - (b.position ?? 0))[0];

  const moveToBacklog = (task: Task) => {
    if (!backlogStatus) {
      toast.error(tr('This project has no Backlog status to move the task to.'));
      return;
    }
    moveTask.mutate(
      { task, statusId: backlogStatus.id },
      {
        onSuccess: () => {
          setBoardSelected((prev) => {
            const next = new Set(prev);
            next.delete(task.id);
            return next;
          });
          toast.success(tr('{key} moved to the Backlog.', { key: task.key }));
        },
        onError: (e) => toast.error(describeApiError(e, tr('Could not move the task to the Backlog.'))),
      },
    );
  };

  const moveToBoard = (task: Task) => {
    if (!target) {
      toast.error(tr('This project has no Board status to move the task to.'));
      return;
    }
    moveTask.mutate(
      { task, statusId: target.id },
      {
        onSuccess: () => toast.success(tr('{key} moved to the Board.', { key: task.key })),
        onError: (e) => toast.error(describeApiError(e, tr('Could not move the task to the Board.'))),
      },
    );
  };

  if (isPending) return <LoadingState title="Loading tasks" text="Fetching this project’s tasks." />;
  if (isError) return <ErrorState title="We couldn’t load tasks" text="Check your connection and try again." onRetry={() => void refetch()} />;

  const filtered = isFiltered(applied);

  const chosen = backlog.filter((t) => selected.has(t.id));
  const allSelected = backlog.length > 0 && chosen.length === backlog.length;
  const toggle = (id: string, checked: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });

  const boardChosen = board.filter((t) => boardSelected.has(t.id));
  const boardAll = board.length > 0 && boardChosen.length === board.length;
  const boardVisible = board.slice(0, boardShown);
  const toggleBoard = (id: string, checked: boolean) =>
    setBoardSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });

  return (
    <div className="task-list-page">
      <TaskFilters filter={filter} onChange={setFilter} onClear={clear} tasks={data.items} combined statuses={statuses} />
      <TaskGroup
        title="Board"
        count={board.length}
        countLabel={board.length === 1 ? 'work item' : 'work items'}
        empty={filtered ? 'No matching board tasks. Try changing or clearing the filters.' : 'No tasks on the Board yet.'}
        selectAll={{
          checked: boardAll,
          indeterminate: boardChosen.length > 0 && !boardAll,
          onChange: (checked) => setBoardSelected(checked ? new Set(board.map((t) => t.id)) : new Set()),
        }}
        action={
          boardChosen.length > 0 && (
            <button type="button" className="outline-btn" onClick={() => boardChosen.forEach(moveToBacklog)}>
              {tr('Move to Backlog')}
            </button>
          )
        }
        footer={
          board.length > boardVisible.length && (
            <div className="task-group-more">
              {tr('Showing {shown} of {total} tasks', { shown: boardVisible.length, total: board.length })} ·{' '}
              <button type="button" className="link-btn" onClick={() => setBoardShown((n) => n + BOARD_PAGE)}>
                {tr('Load more')}
              </button>
            </div>
          )
        }
      >
        {boardVisible.map((t) => (
          <TaskRow key={t.id} task={t} selected={boardSelected.has(t.id)} onSelect={(checked) => toggleBoard(t.id, checked)} />
        ))}
      </TaskGroup>
      <TaskGroup
        title="Backlog"
        count={backlog.length}
        countLabel={backlog.length === 1 ? 'task' : 'tasks'}
        empty={filtered ? 'No matching backlog tasks. Try changing or clearing the filters.' : 'No backlog tasks yet. Tasks here stay off the Board until planned.'}
        selectAll={{
          checked: allSelected,
          indeterminate: chosen.length > 0 && !allSelected,
          onChange: (checked) => setSelected(checked ? new Set(backlog.map((t) => t.id)) : new Set()),
        }}
        action={
          chosen.length > 0 && (
            <button type="button" className="outline-btn" onClick={() => chosen.forEach(moveToBoard)}>
              {tr('Move to Board')}
            </button>
          )
        }
        footer={
          <button type="button" className="create-task" onClick={() => setCreating(true)}>
            <span aria-hidden="true">＋</span> {tr('Create task')}
          </button>
        }
      >
        {backlog.map((t) => (
          <TaskRow
            key={t.id}
            task={t}
            selected={selected.has(t.id)}
            onSelect={(checked) => toggle(t.id, checked)}
            onMoveToBoard={() => moveToBoard(t)}
            moving={moveTask.isPending && moveTask.variables?.task.id === t.id}
          />
        ))}
      </TaskGroup>
      {creating && <QuickCreateTask projectId={project.id} statuses={statuses} onClose={() => setCreating(false)} />}
    </div>
  );
}

export const ProjectMembersPage = () => (
  <PagePlaceholder title="Members" description="Project members and their roles." />
);
