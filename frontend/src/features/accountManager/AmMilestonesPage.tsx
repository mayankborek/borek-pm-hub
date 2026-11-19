import { usePrefs } from '@/shared/prefs/PrefsContext';
import { shortDate } from '@/features/client/format';
import { useProjectContext } from '@/features/client/ClientProjectLayout';
import type { ProjectTaskStatus } from '@/features/client/types';
import './amRoadmap.css';

const DAY = 86_400_000;
const day = (iso: string) => Date.parse(iso + 'T00:00:00Z') / DAY;
const iso = (d: number) => new Date(d * DAY).toISOString().slice(0, 10);

const TASK_COLOR: Record<ProjectTaskStatus, string> = {
  'To do': '#65708A',
  'In progress': '#175DBA',
  'Code review': '#7652C4',
  Testing: '#D88000',
  Blocked: '#C94734',
};
const STATE_LABEL: Record<string, string> = {
  done: 'Done',
  late: 'Running late',
  revised: 'Revised',
  at_risk: 'At risk',
  in_progress: 'In progress',
  planned: 'Not started',
};

/** Milestones tab for Account Managers: milestones and task due dates on one timeline. */
export function AmMilestonesPage() {
  const { project, today } = useProjectContext();
  const { t, lang } = usePrefs();
  const tasks = [...(project.tasks ?? [])].sort((a, b) => a.dueDate.localeCompare(b.dueDate));
  const milestones = [...project.milestones].sort((a, b) => a.dueDate.localeCompare(b.dueDate));

  const dates = [today, ...milestones.flatMap((m) => [m.dueDate, m.requestedDate ?? m.dueDate]), ...tasks.map((x) => x.dueDate)].map(day);
  const start = Math.min(...dates);
  const end = Math.max(...dates);
  const span = Math.max(end - start, 1);
  const frac = (d: string) => (day(d) - start) / span;
  const pos = (d: string) => `${frac(d) * 100}%`;
  const ticks: string[] = [];
  for (let d = start; d <= end; d += 7) ticks.push(iso(d));

  return (
    <section className="amr" aria-label={t('Project roadmap')}>
      <header className="amr-head">
        <div>
          <h2>{t('Project roadmap')}</h2>
          <p>
            {t('Milestones and task due dates · {range}', {
              range: `${shortDate(lang, iso(start))}–${shortDate(lang, iso(end))} ${iso(end).slice(0, 4)}`,
            })}
          </p>
        </div>
        <b>{t('{n} milestones', { n: milestones.length })}</b>
      </header>

      <div className="amr-grid">
        <div className="amr-axis">
          {ticks.map((d) => (
            <span key={d} style={{ left: `calc((100% - var(--amr-label)) * ${frac(d)})` }}>{shortDate(lang, d)}</span>
          ))}
          <em style={{ left: `calc((100% - var(--amr-label)) * ${frac(today)})` }}>{t('Today · {date}', { date: shortDate(lang, today) })}</em>
        </div>

        {milestones.map((m) => {
          const moved = m.requestedDate && m.requestedDate !== m.dueDate;
          const late = m.state === 'late' || m.state === 'revised';
          return (
            <div className="amr-row" key={m.id}>
              <div className="amr-label">
                <small className="amr-kind amr-kind--ms">{t('Milestone')}</small>
                <span>{m.name} · {t(STATE_LABEL[m.state])}</span>
              </div>
              <div className="amr-track">
                <span className={`amr-ms ${late ? 'amr-ms--late' : ''}`} style={{ left: pos(m.dueDate) }}>
                  <i />
                  {moved ? `${shortDate(lang, m.dueDate)} → ${shortDate(lang, m.requestedDate!)}` : shortDate(lang, m.dueDate)}
                </span>
                {moved && (
                  <span className="amr-ms amr-ms--new" style={{ left: pos(m.requestedDate!) }}><i /></span>
                )}
              </div>
            </div>
          );
        })}

        {tasks.map((x) => (
          <div className="amr-row" key={x.id}>
            <div className="amr-label">
              <small className="amr-kind">{t('Task')}</small>
              <span>{x.ref ? `${x.ref} · ` : ''}{x.title} · {t(x.status)}</span>
            </div>
            <div className="amr-track">
              <span className="amr-dot" style={{ left: pos(x.dueDate) }}>
                <i style={{ background: TASK_COLOR[x.status] }} />
                {shortDate(lang, x.dueDate)}
              </span>
            </div>
          </div>
        ))}

        <span className="amr-today" style={{ left: `calc(var(--amr-label) + (100% - var(--amr-label)) * ${frac(today)})` }} aria-hidden="true" />
      </div>

      <footer className="amr-legend">
        <span><i className="amr-sq" />{t('Milestone')}</span>
        <span><i className="amr-circ" />{t('Task due date')}</span>
        <span><i className="amr-dash" />{t('Today')}</span>
      </footer>
    </section>
  );
}
