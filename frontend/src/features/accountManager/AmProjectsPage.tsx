import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { longDate, paddedDate } from '@/features/client/format';
import { nextMilestone, useClientPortal } from '@/features/client/clientPortalApi';
import { HEALTH_LABEL } from '@/features/client/labels';
import { EmptyCard, PortalPending } from '@/features/client/ui';
import { healthBadge } from './amUi';

/** Projects (borek-flow-portal/projects.html): one card per shared project. */
export function AmProjectsPage() {
  const { t, lang } = usePrefs();
  const query = useClientPortal();
  const { data } = query;
  if (!data) return <PortalPending query={query} />;

  const { projects, today } = data;
  if (!projects.length) return <EmptyCard />;
  const by = projects[0].publishedBy;

  return (
    <div className="am-page">
      <h1 style={{ fontSize: 'var(--fs-18)' }}>{t('Projects shared with you')}</h1>
      <p className="lead">{t('Only projects you have been invited to are available here.')}</p>
      <p className="lead" style={{ fontSize: 'var(--fs-11)' }}>
        {by && t('Published {date} · {name}, {role}', { date: paddedDate(lang, projects[0].publishedOn), name: by.name, role: t(by.role) })}
      </p>
      <div className="pcards">
        {projects.map((p) => {
          const next = nextMilestone(p, today);
          return (
            <div className="card pcard" key={p.id}>
              <div className="top"><h3>{p.name}</h3><span className={healthBadge(p.health)}>{t(HEALTH_LABEL[p.health ?? 'none'])}</span></div>
              <p>{t('Published progress')} · {p.progress}%</p>
              <div className="bar"><i style={{ width: `${p.progress}%` }} /></div>
              {next && <p>{t('Next milestone')}: {next.name} · {longDate(lang, next.dueDate)}</p>}
              <Link className="btn" to={paths.amProject(p.id)}>{t('View project')}</Link>
            </div>
          );
        })}
      </div>
    </div>
  );
}
