import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { ProgressBar } from '@/shared/ui/Pill';
import { useProjectContext } from './ProjectLayout';
import { completionOf, formatDate } from './projectUi';
import './projects.css';

export function ProjectOverviewPage() {
  const project = useProjectContext();
  const s = project.task_summary;

  const stats = [
    { label: 'Total tasks', value: s?.total },
    { label: 'Completed', value: s?.completed },
    { label: 'In progress', value: s?.in_progress },
    { label: 'Blocked', value: s?.blocked, tone: s?.blocked ? 'err' : '' },
    { label: 'Overdue', value: s?.overdue, tone: s?.overdue ? 'warn' : '' },
  ];

  return (
    <div className="overview">
      <section className="card" aria-label="Task progress">
        <h3>Progress</h3>
        <p className="desc">Completed tasks out of all tasks, excluding cancelled.</p>
        <div className="big-progress">
          <ProgressBar percent={completionOf(project)} label="Project completion" />
        </div>
        <div className="stat-grid">
          {stats.map((st) => (
            <div className="stat" key={st.label}>
              <span className="stat-label">{st.label}</span>
              <strong className={st.tone ?? ''}>{st.value ?? '—'}</strong>
            </div>
          ))}
        </div>
        <div className="link-row">
          <Link className="btn" to={paths.projectBoard(project.id)}>
            View board
          </Link>
          <Link className="btn secondary" to={paths.projectList(project.id)}>
            View backlog
          </Link>
          <Link className="btn secondary" to={`${paths.tasks}?project_id=${project.id}`}>
            All tasks for this project
          </Link>
        </div>
      </section>

      <section className="card" aria-label="Project details">
        <h3>Details</h3>
        <dl className="details">
          <dt>Code</dt>
          <dd>{project.code}</dd>
          <dt>Start date</dt>
          <dd>{formatDate(project.start_date)}</dd>
          <dt>Target end</dt>
          <dd>{formatDate(project.target_end_date)}</dd>
          <dt>Description</dt>
          <dd className="pre">{project.description || 'No description provided.'}</dd>
        </dl>
      </section>
    </div>
  );
}
