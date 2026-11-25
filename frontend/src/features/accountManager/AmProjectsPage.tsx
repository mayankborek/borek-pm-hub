import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { longDate } from '@/features/client/format';
import { useClientPortal } from '@/features/client/clientPortalApi';
import { HEALTH_LABEL } from '@/features/client/labels';
import { Icon } from '@/features/client/icons';
import { EmptyCard, PortalPending } from '@/features/client/ui';
import '@/features/client/clientScreens.css';

/** Projects (design.html): one card per project beside a portfolio summary. */
export function AmProjectsPage() {
  const { t, lang } = usePrefs();
  const query = useClientPortal();
  const { data } = query;
  if (!data) return <PortalPending query={query} />;

  const { projects, organisation } = data;
  if (!projects.length) return <EmptyCard />;
  const external = projects.filter((p) => p.organisation).length;
  const started = projects.filter((p) => p.progress !== null).length;

  return (
    <div className="cp">
      <section className="cx-welcome">
        <h1>{t('Projects')}</h1>
        <p>{t('Projects of your clients and projects you are a member of.')}</p>
      </section>
      <div className="cx-sec">
        <h2>{t('All projects · {n}', { n: projects.length })}</h2>
      </div>
      <div className="am-pj">
        <section className="am-pj-grid">
          {projects.map((p) => (
            <article className="cx-card cx-pcard" key={p.id}>
              <div className="cx-hd">
                <span className="cx-picon"><Icon name={p.organisation ? 'briefcase' : 'layers'} className="cx-ico cx-22" strokeWidth={1.6} /></span>
                <div>
                  <h3>{p.name}</h3>
                  <div className="cx-co">{p.organisation ?? organisation} · {t(p.organisation ? 'Client project' : 'Internal initiative')}</div>
                </div>
              </div>
              <div className="cx-tags">
                <span className="cx-tag">{t(p.organisation ? 'External' : 'Internal')}</span>
                <span className="cx-tag">{t(p.progress === null ? 'Planned' : 'In Progress')}</span>
                <span className={`cx-tag cx-${p.health ?? 'none'}`}>{t(HEALTH_LABEL[p.health ?? 'none'])}</span>
              </div>
              <div className="cx-prow"><span>{t('Task completion')}</span><b>{p.progress ?? '–'}{p.progress !== null && '%'}</b></div>
              <div className="cx-bar" role="progressbar" aria-valuenow={p.progress ?? undefined} aria-valuemin={0} aria-valuemax={100}>
                <i style={{ width: `${p.progress ?? 0}%` }} />
              </div>
              <p className="cx-due">{p.dueDate ? t('Due {date}', { date: longDate(lang, p.dueDate) }) : t('Dates to be planned')}</p>
              <p className="cx-due"><Link to={paths.amProject(p.id)}>{t('View project')} →</Link></p>
            </article>
          ))}
        </section>
        <aside className="cx-card am-pj-side">
          <h3>{t('Your Portfolio')}</h3>
          <div className="am-pj-n">{t('{n} projects', { n: projects.length })}</div>
          <h4>{t('By status')}</h4>
          <div className="am-pj-tiles">
            <div><span>{t('In Progress')}</span><b>{started}</b></div>
            <div><span>{t('Planned')}</span><b>{projects.length - started}</b></div>
          </div>
          <h4>{t('By project type')}</h4>
          <dl>
            <div><dt>{t('External project')}</dt><dd>{external}</dd></div>
            <div><dt>{t('Internal project')}</dt><dd>{projects.length - external}</dd></div>
          </dl>
        </aside>
      </div>
    </div>
  );
}
