import { Link } from 'react-router-dom';
import { usePortalPaths } from './portalPaths';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { dayMonth, initialsOf, longDate, paddedDate } from './format';
import { nextMilestone } from './clientPortalApi';
import { MILESTONE_BADGE } from './labels';
import { useProjectContext } from './ClientProjectLayout';
import { Icon } from './icons';
import './clientScreens.css';

const SEGMENTS = 25;
const DAY = 86_400_000;
const daysBetween = (from: string, to: string) => Math.max(0, Math.round((Date.parse(to) - Date.parse(from)) / DAY));

export function ClientOverviewPage() {
  const pp = usePortalPaths();
  const { project, today } = useProjectContext();
  const { t, lang } = usePrefs();

  const next = nextMilestone(project, today);
  const done = project.milestones.filter((m) => m.state === 'done').length;
  const filled = Math.round((project.progress / 100) * SEGMENTS);
  const inReview = project.changeRequests.find((c) => c.status === 'in_review');
  const manager = project.publishedBy;
  const nextDate = next && dayMonth(lang, next.dueDate).split(' ');

  return (
    <div className="cx-ov">
      <div className="cx-col">
        <section className="cx-card cx-pp">
          <div className="cx-hd2">
            <span className="cx-lh"><Icon name="chart" /> {t('Project progress')}</span>
            <span className="cx-dt">{paddedDate(lang, project.publishedOn)}</span>
          </div>
          <div className="cx-big">
            <strong>{project.progress}%</strong>
            <div>
              <div className="cx-t">{t('Latest published progress')}</div>
              <div className="cx-s">{t('Shared by {name}', { name: manager.name })}</div>
            </div>
          </div>
          <div className="cx-segs" role="img" aria-label={t('{n} percent progress', { n: project.progress })}>
            {Array.from({ length: SEGMENTS }, (_, i) => <i key={i} className={i < filled ? 'cx-f' : undefined} />)}
          </div>
          <p className="cx-trend">{t('A progress trend will appear when more updates are shared.')}</p>
          <hr />
          <div className="cx-dates">
            <div><div className="cx-k">{t('Started')}</div><div className="cx-v">{longDate(lang, project.startDate)}</div></div>
            <div><div className="cx-k">{t('Target completion')}</div><div className="cx-v">{longDate(lang, project.dueDate)}</div></div>
          </div>
        </section>

        <section className="cx-card cx-lu">
          <div className="cx-hd2">
            <span className="cx-lh"><Icon name="file" /> {t('Latest project update')}</span>
            {project.latestUpdate && <span className="cx-dt">{paddedDate(lang, project.latestUpdate.date)}</span>}
          </div>
          <p>{project.latestUpdate ? project.latestUpdate.text : t('No updates have been shared yet.')}</p>
          <hr />
          <div className="cx-by">
            <div className="cx-who">
              <span className="cx-avatar" aria-hidden="true">{initialsOf(manager.name)}</span>
              <div><b>{manager.name}</b><span className="cx-r">{t(manager.role)}</span></div>
            </div>
            <Link to={pp.reports(project.id)}>
              {t('View reports')} <Icon name="arrow" className="cx-ico cx-11" />
            </Link>
          </div>
        </section>
      </div>

      <div className="cx-col cx-right">
        <div className="cx-kpis">
          <div className="cx-card cx-kpi">
            <Icon name="flag" />
            <div className="cx-n">{done} / {project.milestones.length}</div>
            <div className="cx-l">{t('Milestones')}</div>
            <div className="cx-s">{t('Completed')}</div>
          </div>
          <div className="cx-card cx-kpi">
            <Icon name="calendar" />
            <div className="cx-n">{daysBetween(today, project.dueDate)}</div>
            <div className="cx-l">{t('Days left')}</div>
            <div className="cx-s">{t('Until {date}', { date: dayMonth(lang, project.dueDate) })}</div>
          </div>
          <div className="cx-card cx-kpi">
            <Icon name="check" />
            <div className="cx-n">{project.clientActions}</div>
            <div className="cx-l">{t('Client actions')}</div>
            <div className="cx-s">{project.clientActions ? t('Waiting on you') : t('Nothing pending')}</div>
          </div>
        </div>

        <section className="cx-card cx-nm">
          <h3>{t('Next milestone')}</h3>
          {next && nextDate ? (
            <div className="cx-row">
              <div className="cx-box"><b>{nextDate[0]}</b><small>{(nextDate[1] ?? '').toUpperCase()}</small></div>
              <div>
                <div className="cx-t">{next.name}</div>
                <div className="cx-s">
                  {next.state === 'planned' ? t('Not started') : t(MILESTONE_BADGE[next.state].label)} · {longDate(lang, next.dueDate)}
                </div>
              </div>
            </div>
          ) : (
            <p className="cx-s" style={{ marginTop: 17 }}>{t('Nothing planned')}</p>
          )}
          <Link className="cx-more" to={pp.milestones(project.id)}>
            {t('View milestones')} <Icon name="arrow" className="cx-ico cx-11" strokeWidth={2} />
          </Link>
        </section>

        <section className="cx-card cx-ra">
          <div className="cx-hd2">
            <span className="cx-lh"><Icon name="activity" /> {t('Recent activity')}</span>
          </div>
          <div className="cx-box">
            {inReview ? (
              <>
                <div className="cx-t">{t('Change request in review')}</div>
                <div className="cx-s">{inReview.ref} · {inReview.title}</div>
                <Link to={pp.changeRequests(project.id)}>
                  {t('View request')} <Icon name="arrow" className="cx-ico cx-11" strokeWidth={2} />
                </Link>
              </>
            ) : (
              <div className="cx-s">{t('No recent activity.')}</div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
