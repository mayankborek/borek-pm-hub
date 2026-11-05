import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { LoadingState } from '@/shared/ui/States';
import { longDate, paddedDate } from './format';
import { nextMilestone, useClientPortal } from './clientPortalApi';
import { HEALTH_LABEL, HEALTH_TONE } from './labels';
import { Badge, Bar } from './ui';

export function ClientProjectsPage() {
  const { t, lang } = usePrefs();
  const { data, isLoading } = useClientPortal();
  if (isLoading || !data) return <LoadingState />;

  const published = data.projects[0];
  return (
    <>
      <h3 className="cp-sec" style={{ marginTop: 24 }}>{t('Projects shared with you')}</h3>
      <p className="cp-sub" style={{ marginTop: 20 }}>{t('Only projects you have been invited to are available here.')}</p>
      {published && (
        <p className="cp-small" style={{ marginTop: 16 }}>
          {t('Published {date} · {name}, {role}', {
            date: paddedDate(lang, published.publishedOn),
            name: published.publishedBy.name,
            role: t(published.publishedBy.role),
          })}
        </p>
      )}
      <div className="cp-pcards">
        {data.projects.map((p) => {
          const next = nextMilestone(p, data.today);
          return (
            <div className="cp-card cp-pc" key={p.id}>
              <div className="cp-top2">
                <b>{p.name}</b>
                <Badge tone={HEALTH_TONE[p.health]}>{t(HEALTH_LABEL[p.health])}</Badge>
              </div>
              <p style={{ marginTop: 14, fontSize: 13 }}>{t('Published progress · {n}%', { n: p.progress })}</p>
              <Bar value={p.progress} />
              {next && (
                <p style={{ fontSize: 14 }}>
                  {t('Next milestone: {name} · {date}', { name: next.name, date: longDate(lang, next.dueDate) })}
                </p>
              )}
              <Link className="cp-btn" to={paths.clientProject(p.id)}>{t('View project')}</Link>
            </div>
          );
        })}
      </div>
    </>
  );
}
