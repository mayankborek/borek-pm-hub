import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { paths } from '@/app/routes';
import { api } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useProjectContext } from '@/features/projects/ProjectLayout';
import { QuickCreateTask } from '@/features/tasks/QuickCreateTask';
import { useProjectStatuses, useProjectTasks, type Task } from '@/features/tasks/tasksApi';
import { PRIORITY_LABEL } from '@/features/accountManager/amWork';
import { Avatar, FilterBar, Pager, fmtDate, statusTone, useDevFilter } from './devUi';

const PAGE = 10;

/** Mirrors the fields of backend SprintOut that the Backlog header shows. */
interface Sprint {
  id: string;
  name: string;
  state: 'planned' | 'active' | 'completed';
  start_date: string | null;
  end_date: string | null;
}

function TaskTable({ rows, empty, soft }: { rows: Task[]; empty: string; soft?: boolean }) {
  const { t } = usePrefs();
  return (
    <table className={soft ? 'dv-table soft' : 'dv-table'}>
      <thead>
        <tr><th>{t('Task')}</th><th>{t('Status')}</th><th>{t('Due date')}</th><th>{t('Priority')}</th><th>{t('Assignee')}</th></tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr className="empty"><td colSpan={5}>{empty}</td></tr>
        ) : (
          rows.map((x) => (
            <tr key={x.id}>
              <td><Link to={paths.task(x.id)}>{x.key} · {x.title}</Link></td>
              <td style={{ color: statusTone(x.status.name, x.status.category) }}>{t(x.status.name)}</td>
              <td className="muted">{fmtDate(x.due_date)}</td>
              <td className="muted">{t(PRIORITY_LABEL[x.priority])}</td>
              <td>
                {x.assignee ? <span className="dv-person"><Avatar name={x.assignee.name} size={24} />{x.assignee.name}</span> : <span className="muted">{t('Unassigned')}</span>}
              </td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

/** Backlog tab (borek-flow-screens): the sprint's planned work above the Backlog, ten tasks per page. */
export function DevBacklogPage() {
  const { t } = usePrefs();
  const project = useProjectContext();
  const f = useDevFilter();
  const [creating, setCreating] = useState(false);
  const [boardPage, setBoardPage] = useState(1);
  const [backlogPage, setBacklogPage] = useState(1);
  const { data: statuses } = useProjectStatuses(project.id);
  const { data, isPending, isError, refetch } = useProjectTasks(project.id, f.filter);
  const sprints = useQuery({ queryKey: ['projects', 'sprints', project.id], queryFn: () => api<{ items: Sprint[] }>(`/projects/${project.id}/sprints`), retry: false });

  const board = useMemo(() => (data?.items ?? []).filter((x) => x.status.category !== 'backlog'), [data]);
  const backlog = useMemo(() => (data?.items ?? []).filter((x) => x.status.category === 'backlog'), [data]);
  const items = sprints.data?.items ?? [];
  const sprint = items.find((s) => s.state === 'active') ?? items.find((s) => s.state === 'planned');

  if (isPending) return <LoadingState title="Loading tasks" text="Fetching this project’s tasks." />;
  if (isError) return <ErrorState title="We couldn’t load tasks" text="Check your connection and try again." onRetry={() => void refetch()} />;

  const filtered = !!(f.filter.q || f.filter.statusId || f.filter.priority);
  const pageOf = (rows: Task[], page: number) => rows.slice((page - 1) * PAGE, page * PAGE);

  return (
    <>
      <FilterBar f={f} statuses={statuses ?? []} />
      <section className="dv-card-box" aria-label={sprint?.name ?? t('Board')}>
        <header>
          <h3>{sprint?.name ?? t('No active sprint')}</h3>
          {sprint && <span className={sprint.state === 'active' ? 'dv-badge' : 'dv-badge plan'}>{t(sprint.state === 'active' ? 'Active' : 'Planned')}</span>}
          {sprint && (
            <span className="dv-dates">
              <span>{fmtDate(sprint.start_date)}</span>
              <span>–</span>
              <span>{fmtDate(sprint.end_date)}</span>
            </span>
          )}
        </header>
        <TaskTable rows={pageOf(board, boardPage)} empty={filtered ? t('No matching board tasks. Try changing or clearing the filters.') : t('No tasks on the Board yet.')} />
        <Pager page={boardPage} total={board.length} size={PAGE} onPage={setBoardPage} />
      </section>

      <section className="dv-card-box" aria-label={t('Backlog')}>
        <header><h3>{t('Backlog')}</h3></header>
        <TaskTable soft rows={pageOf(backlog, backlogPage)} empty={filtered ? t('No matching backlog tasks. Try changing or clearing the filters.') : t('No backlog tasks yet. Tasks here stay off the Board until planned.')} />
        <button type="button" className="dv-create" onClick={() => setCreating(true)}><span aria-hidden="true">+</span> {t('Create task')}</button>
        <Pager page={backlogPage} total={backlog.length} size={PAGE} onPage={setBacklogPage} />
      </section>
      {creating && <QuickCreateTask projectId={project.id} statuses={statuses} onClose={() => setCreating(false)} />}
    </>
  );
}
