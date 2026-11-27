import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { paths } from '@/app/routes';
import { api, describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useToast } from '@/shared/ui/Toast';
import { useProjectTasks, emptyFilter, type Task } from '@/features/tasks/tasksApi';
import { useProjectContext } from './ProjectLayout';
import { formatDate, todayIso } from './projectUi';
import './sprintPlanning.css';

/** Mirrors the fields of backend SprintOut that this page shows. */
interface Sprint {
  id: string;
  name: string;
  goal: string | null;
  state: 'planned' | 'active' | 'completed';
  start_date: string | null;
  end_date: string | null;
  version: number;
}

const sprintKey = (projectId: string) => ['projects', 'sprints', projectId] as const;

/** Last day of a sprint that starts on `start` and runs `weeks` weeks (YYYY-MM-DD in, YYYY-MM-DD out). */
function endDate(start: string, weeks: number) {
  const [y, m, d] = start.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + weeks * 7 - 1)).toISOString().slice(0, 10);
}

/** Create sprint dialog (sprint-planning.html): name, goal, 1 or 2 weeks, start date. Saved as Planned. */
function CreateSprint({ projectId, nextName, onClose }: { projectId: string; nextName: string; onClose: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const qc = useQueryClient();
  const ref = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState(nextName);
  const [goal, setGoal] = useState('');
  const [weeks, setWeeks] = useState(2);
  const [start, setStart] = useState(todayIso());
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  const create = useMutation({
    mutationFn: () =>
      api(`/projects/${projectId}/sprints`, {
        method: 'POST',
        body: JSON.stringify({ name: name.trim() || null, goal: goal.trim() || null, start_date: start, end_date: endDate(start, weeks) }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: sprintKey(projectId) });
      ref.current?.close();
    },
    onError: (e) => toast.error(describeApiError(e, t('Could not add the sprint.'))),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (start) create.mutate();
  };
  return (
    <dialog ref={ref} className="spd" aria-labelledby="spd-t" onClose={onClose}>
      <form onSubmit={submit}>
        <div className="spd-head">
          <h2 id="spd-t">{t('Create sprint')}</h2>
          <button type="button" className="spd-x" aria-label={t('Close')} onClick={() => ref.current?.close()}>×</button>
        </div>
        <p className="spd-hint">{t('Plan a focused week or two. Add tasks after creating the sprint.')}</p>
        <label htmlFor="spd-name">{t('Sprint name')}</label>
        <input id="spd-name" type="text" required value={name} onChange={(e) => setName(e.target.value)} />
        <label htmlFor="spd-goal">{t('Sprint goal (optional)')}</label>
        <input id="spd-goal" type="text" value={goal} onChange={(e) => setGoal(e.target.value)} />
        <fieldset>
          <legend>{t('Duration')}</legend>
          <div className="spd-seg">
            {[1, 2].map((w) => (
              <button key={w} type="button" aria-pressed={weeks === w} onClick={() => setWeeks(w)}>
                {t(w === 1 ? '1 week' : '2 weeks')}
              </button>
            ))}
          </div>
        </fieldset>
        <label htmlFor="spd-start">{t('Start date')}</label>
        <input id="spd-start" type="date" required value={start} onChange={(e) => setStart(e.target.value)} />
        <p className="spd-hint">
          {start ? t('Ends {date} · {n} calendar days', { date: formatDate(endDate(start, weeks)), n: weeks * 7 }) : t('Pick a start date')}
        </p>
        <p className="spd-hint">{t('Saved as Planned. Your active sprint will keep running.')}</p>
        <div className="spd-foot">
          <button type="button" className="btn secondary" onClick={() => ref.current?.close()}>{t('Cancel')}</button>
          <button type="submit" className="btn" disabled={create.isPending || !start}>{t('Create sprint')}</button>
        </div>
      </form>
    </dialog>
  );
}

/** One task row: key and title, status, assignee and the add action. */
function TaskRow({ task, action }: { task: Task; action: { text: string; disabled: boolean; onClick: () => void } }) {
  const { t } = usePrefs();
  return (
    <div className="sp-row">
      <Link className="sp-title" to={paths.task(task.id)}>{task.key} · {task.title}</Link>
      <span>{t(task.status.name)}</span>
      <span>{task.assignee?.name ?? t('Unassigned')}</span>
      <button type="button" disabled={action.disabled} onClick={action.onClick}>{action.text}</button>
    </div>
  );
}

/**
 * Sprint Planning tab, ahead of the Board (sprint-planning.html): shows the active sprint, lets a PM create the next
 * sprint, and moves backlog tasks into it. Planned work is the project's non-Backlog tasks, as in the Backlog tab.
 */
export function SprintPlanningPage() {
  const { t } = usePrefs();
  const toast = useToast();
  const qc = useQueryClient();
  const project = useProjectContext();
  const [creating, setCreating] = useState(false);
  const sprints = useQuery({ queryKey: sprintKey(project.id), queryFn: () => api<{ items: Sprint[] }>(`/projects/${project.id}/sprints`), retry: false });
  const tasks = useProjectTasks(project.id, emptyFilter);

  const items = sprints.data?.items ?? [];
  const active = items.find((s) => s.state === 'active');
  const planned = items.find((s) => s.state === 'planned');
  const all = tasks.data?.items ?? [];
  const backlog = all.filter((k) => k.status.category === 'backlog');
  const inSprint = all.filter((k) => k.status.category !== 'backlog');

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: sprintKey(project.id) });
    void qc.invalidateQueries({ queryKey: ['projects', project.id] });
    void qc.invalidateQueries({ queryKey: ['tasks'] });
  };
  const add = useMutation({
    mutationFn: (task: Task) =>
      api(`/projects/${project.id}/sprints/move-tasks`, { method: 'POST', body: JSON.stringify({ task_ids: [task.id], sprint_id: planned?.id }) }),
    onSuccess: refresh,
    onError: (e) => toast.error(describeApiError(e, t('Could not add the tasks.'))),
  });
  const start = useMutation({
    mutationFn: (s: Sprint) => api(`/projects/${project.id}/sprints/${s.id}/start`, { method: 'POST', body: JSON.stringify({ version: s.version }) }),
    onSuccess: refresh,
    onError: (e) => toast.error(describeApiError(e, t('Could not update the sprint.'))),
  });

  if (sprints.isPending || tasks.isPending) return <LoadingState title="Loading sprint planning" text="Fetching this project’s sprints and tasks." />;
  if (sprints.isError || tasks.isError)
    return <ErrorState title="We couldn’t load sprint planning" text="Check your connection and try again." onRetry={() => { void sprints.refetch(); void tasks.refetch(); }} />;

  const nextName = `Sprint ${String(items.length + 1).padStart(2, '0')}`;
  const range = (s: Sprint) => `${formatDate(s.start_date)} – ${formatDate(s.end_date)}`;
  const count = (n: number) => t(n === 1 ? '{n} task' : '{n} tasks', { n });

  return (
    <div className="sp">
      <div className="sp-head">
        <h2>{t('Backlog & sprint planning')}</h2>
        <div className="sp-acts">
          <Link className="btn secondary" to={paths.projectBoard(project.id)}>{t('Active board')}</Link>
          <button type="button" className="btn" disabled={!!planned} onClick={() => setCreating(true)}>{t('Create sprint')}</button>
        </div>
      </div>

      {active && (
        <section className="sp-card" aria-label={active.name}>
          <h3>{active.name} · {t('Active')}</h3>
          <p>{range(active)}</p>
          {active.goal && <p>{t('Goal: {goal}', { goal: active.goal })}</p>}
        </section>
      )}

      {planned ? (
        <section className="sp-card" id="planned" aria-label={planned.name}>
          <div className="sp-card-top">
            <h3>{planned.name} · {t('Planned')}</h3>
            <button type="button" className="btn" disabled={!!active || start.isPending} onClick={() => start.mutate(planned)}>{t('Start sprint')}</button>
          </div>
          <p>{range(planned)} · {count(inSprint.length)}</p>
          {planned.goal && <p className="sp-goal">{t('Goal: {goal}', { goal: planned.goal })}</p>}
          {active && <p className="sp-note">{t('Add work below. Finish {name} before starting this sprint.', { name: active.name })}</p>}
          {inSprint.map((k) => (
            <TaskRow key={k.id} task={k} action={{ text: t('In {name}', { name: planned.name }), disabled: true, onClick: () => undefined }} />
          ))}
        </section>
      ) : (
        <section className="sp-card" id="empty">
          <div className="sp-card-top">
            <div>
              <h3>{t('Plan the next sprint')}</h3>
              <p>{t('Create a 1- or 2-week sprint, then add tasks from the backlog.')}</p>
            </div>
            <button type="button" className="btn" onClick={() => setCreating(true)}>{t('Create sprint')}</button>
          </div>
        </section>
      )}

      <section className="sp-card sp-backlog" aria-label={t('Backlog')}>
        <h3>{t('Backlog')} · {count(backlog.length)}</h3>
        <p>{t('Work waiting to be planned. Add tasks to a planned sprint before starting it.')}</p>
        {backlog.map((k) => (
          <TaskRow
            key={k.id}
            task={k}
            action={{
              text: planned ? t('Add to {name}', { name: planned.name }) : t('Plan sprint first'),
              disabled: !planned || add.isPending,
              onClick: () => add.mutate(k),
            }}
          />
        ))}
      </section>

      {creating && <CreateSprint projectId={project.id} nextName={nextName} onClose={() => setCreating(false)} />}
    </div>
  );
}
