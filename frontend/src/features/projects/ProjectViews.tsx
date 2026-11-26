import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { PagePlaceholder } from '@/shared/ui/PagePlaceholder';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { QuickCreateTask } from '@/features/tasks/QuickCreateTask';
import { Avatar, PRIORITY_LABEL, TaskFilters } from '@/features/tasks/TaskParts';
import { PRIORITY_OPTIONS } from '@/features/tasks/PrioritySelect';
import { isFiltered, useUrlFilter } from '@/features/tasks/useUrlFilter';
import { useMoveTask, useProjectStatuses, useProjectTasks, type Task } from '@/features/tasks/tasksApi';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { useProjectContext } from './ProjectLayout';
import { ManagePhases } from './ManagePhases';
import { SprintBar } from './SprintBar';
import { formatDate } from './projectUi';
import './backlog.css';

const PER_PAGE = 10;

/** One task table of the Backlog tab (borek-flow-backlog2.html): Task, Status, Due date, Priority, Assignee. */
function TaskTable({ tasks, label, action }: { tasks: Task[]; label: string; action?: { text: string; onClick: (t: Task) => void; busy?: string } }) {
  const { t: tr } = usePrefs();
  return (
    <div className="scroll">
      <table aria-label={label}>
        <colgroup>
          <col /><col className="c-status" /><col className="c-due" /><col className="c-pri" /><col className="c-who" />
          {action && <col className="c-act" />}
        </colgroup>
        <thead>
          <tr>
            <th scope="col">{tr('Task')}</th>
            <th scope="col">{tr('Status')}</th>
            <th scope="col">{tr('Due date')}</th>
            <th scope="col">{tr('Priority')}</th>
            <th scope="col">{tr('Assignee')}</th>
            {action && <th scope="col"><span className="sr-only">{tr('Actions')}</span></th>}
          </tr>
        </thead>
        <tbody>
          {tasks.map((k) => {
            const pri = PRIORITY_OPTIONS.find((o) => o.value === k.priority) ?? PRIORITY_OPTIONS[2];
            return (
              <tr key={k.id}>
                <th scope="row"><Link to={paths.task(k.id)}>{k.key} · {k.title}</Link></th>
                <td className={`cat-${k.status.category} st-${k.status.name.toLowerCase().replace(/\s+/g, '-')}`}>{tr(k.status.name)}</td>
                <td>{k.due_date ? <time dateTime={k.due_date}>{formatDate(k.due_date)}</time> : '—'}</td>
                <td className={`pr-${k.priority}`}><span className="pri"><img src={pri.icon} alt="" width={16} height={16} />{tr(PRIORITY_LABEL[k.priority])}</span></td>
                <td>
                  {k.assignee ? <span className="who"><Avatar user={k.assignee} round />{k.assignee.name}</span> : tr('Unassigned')}
                </td>
                {action && (
                  <td><button type="button" className="row-act" disabled={action.busy === k.id} onClick={() => action.onClick(k)}>{action.text}</button></td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Backlog tab: a Sprint sheet (planned work, 10 per page) above the Backlog sheet; new tasks land in Backlog by default. */
export function ProjectListPage() {
  const project = useProjectContext();
  const [creating, setCreating] = useState(false);
  const [phases, setPhases] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [page, setPage] = useState(1);
  const isPm = useAuth().user?.role === 'pm';
  const { filter, applied, setFilter, clear } = useUrlFilter();
  const { data: statuses } = useProjectStatuses(project.id);
  const { data, isPending, isError, refetch } = useProjectTasks(project.id, applied);

  const backlog = useMemo(() => (data?.items ?? []).filter((t) => t.status.category === 'backlog'), [data]);
  const board = useMemo(() => (data?.items ?? []).filter((t) => t.status.category !== 'backlog'), [data]);
  const { t: tr } = usePrefs();
  const toast = useToast();
  const moveTask = useMoveTask();

  const pages = Math.max(1, Math.ceil(board.length / PER_PAGE));
  const current = Math.min(page, pages);
  const shown = board.slice((current - 1) * PER_PAGE, current * PER_PAGE);
  const filterKey = JSON.stringify(applied);
  useEffect(() => setPage(1), [filterKey]);

  // A planned task starts in the first "To do" status, else the first non-Backlog status on the Board.
  const boardStatuses = [...(statuses ?? [])].filter((s) => s.category !== 'backlog').sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
  const target = boardStatuses.find((s) => s.category === 'todo') ?? boardStatuses[0];
  const backlogStatus = [...(statuses ?? [])].filter((s) => s.category === 'backlog').sort((a, b) => (a.position ?? 0) - (b.position ?? 0))[0];

  const moveTo = (task: Task, status: { id: string } | undefined, ok: string, missing: string, failed: string) => {
    if (!status) {
      toast.error(tr(missing));
      return;
    }
    moveTask.mutate(
      { task, statusId: status.id },
      {
        onSuccess: () => toast.success(tr(ok, { key: task.key })),
        onError: (e) => toast.error(describeApiError(e, tr(failed))),
      },
    );
  };
  const moveToBacklog = (task: Task) =>
    moveTo(task, backlogStatus, '{key} moved to the Backlog.', 'This project has no Backlog status to move the task to.', 'Could not move the task to the Backlog.');
  const moveToBoard = (task: Task) =>
    moveTo(task, target, '{key} moved to the Board.', 'This project has no Board status to move the task to.', 'Could not move the task to the Board.');
  const busy = moveTask.isPending ? moveTask.variables?.task.id : undefined;

  if (isPending) return <LoadingState title="Loading tasks" text="Fetching this project’s tasks." />;
  if (isError) return <ErrorState title="We couldn’t load tasks" text="Check your connection and try again." onRetry={() => void refetch()} />;

  const filtered = isFiltered(applied);
  const from = board.length ? (current - 1) * PER_PAGE + 1 : 0;

  return (
    <div className="task-list-page bl2">
      <TaskFilters
        filter={filter}
        onChange={setFilter}
        onClear={clear}
        tasks={data.items}
        combined
        statuses={statuses}
        trailing={
          isPm && (
            <button type="button" className="more" aria-label={tr('Manage phases')} title={tr('Manage phases')} onClick={() => setPhases(true)}>•••</button>
          )
        }
      />
      <section className="sheet" aria-label={tr('Sprint')}>
        <SprintBar projectId={project.id} projectName={project.name} collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
        {!collapsed && (
          <>
            {board.length === 0 ? (
              <p className="sheet-empty">{tr(filtered ? 'No matching board tasks. Try changing or clearing the filters.' : 'No tasks on the Board yet.')}</p>
            ) : (
              <TaskTable tasks={shown} label={tr('Sprint')} action={isPm ? { text: tr('Move to Backlog'), onClick: moveToBacklog, busy } : undefined} />
            )}
            <div className="pager">
              <p>{tr('Showing {from}–{to} of {total} tasks · {n} per page', { from, to: from + Math.max(shown.length - 1, 0), total: board.length, n: PER_PAGE })}</p>
              <nav aria-label={tr('Pagination')}>
                <button type="button" disabled={current === 1} onClick={() => setPage(current - 1)}>{tr('Previous')}</button>
                {Array.from({ length: pages }, (_, i) => i + 1).map((n) => (
                  <button key={n} type="button" aria-current={n === current ? 'page' : undefined} onClick={() => setPage(n)}>{n}</button>
                ))}
                <button type="button" disabled={current === pages} onClick={() => setPage(current + 1)}>{tr('Next')}</button>
              </nav>
            </div>
          </>
        )}
      </section>
      <section className="sheet backlog" aria-label={tr('Backlog')}>
        <h2>{tr('Backlog')}</h2>
        {backlog.length === 0 ? (
          <p className="sheet-empty">{tr(filtered ? 'No matching backlog tasks. Try changing or clearing the filters.' : 'No backlog tasks yet. Tasks here stay off the Board until planned.')}</p>
        ) : (
          <TaskTable tasks={backlog} label={tr('Backlog')} action={isPm ? { text: tr('Move to Board'), onClick: moveToBoard, busy } : undefined} />
        )}
        <button type="button" className="create-task" onClick={() => setCreating(true)}>
          <span aria-hidden="true">＋</span> {tr('Create task')}
        </button>
      </section>
      {creating && <QuickCreateTask projectId={project.id} statuses={statuses} onClose={() => setCreating(false)} />}
      {phases && <ManagePhases projectId={project.id} onClose={() => setPhases(false)} />}
    </div>
  );
}

export const ProjectMembersPage = () => (
  <PagePlaceholder title="Members" description="Project members and their roles." />
);
