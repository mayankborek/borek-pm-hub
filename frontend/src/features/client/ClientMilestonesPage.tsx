import { Link } from 'react-router-dom';
import { usePortalPaths } from './portalPaths';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { longDate, paddedDate, shortDate } from './format';
import { useProjectContext } from './ClientProjectLayout';
import { MILESTONE_BADGE, MILESTONE_STATUS } from './labels';
import { Kpi, MilestoneCard } from './ui';

export function ClientMilestonesPage() {
  const pp = usePortalPaths();
  const { project, today } = useProjectContext();
  const { t, lang } = usePrefs();

  const milestones = [...project.milestones].sort((a, b) => a.dueDate.localeCompare(b.dueDate));
  const manager = project.publishedBy;
  const startIso = project.startDate ?? today;
  const dueIso = project.dueDate ?? today;

  const DAY = 86_400_000;
  const day = (iso: string) => Date.parse(iso + 'T00:00:00Z') / DAY;
  const start = Math.min(day(startIso), day(today), ...milestones.map((m) => day(m.dueDate)));
  const end = Math.max(day(dueIso), day(today), ...milestones.map((m) => day(m.requestedDate ?? m.dueDate)));
  const span = Math.max(end - start, 1);
  const pct = (iso: string) => `${((day(iso) - start) / span) * 100}%`;
  const ticks = Array.from({ length: 5 }, (_, i) => new Date((start + (span * i) / 4) * DAY).toISOString().slice(0, 10));
  const range = `${shortDate(lang, new Date(start * DAY).toISOString().slice(0, 10))}–${longDate(lang, new Date(end * DAY).toISOString().slice(0, 10))}`;

  const openCrs = project.changeRequests.filter((c) => c.status === 'pending' || c.status === 'in_review');
  const awaiting = project.changeRequests.filter((c) => c.status === 'in_review').length;
  const cardMeta = (m: (typeof milestones)[number]) => {
    const n = m.progress ?? 0;
    if (m.state === 'revised' && m.requestedDate) {
      return t('Published revision: {from} → {to} · {n}%', { from: shortDate(lang, m.dueDate), to: longDate(lang, m.requestedDate), n });
    }
    return t('Baseline {from} · Proposed {to} · {n}%', { from: longDate(lang, m.dueDate), to: longDate(lang, m.requestedDate ?? m.dueDate), n });
  };

  return (
    <>
    <section className="cp-card cp-rm" aria-label={t('Project roadmap')}>
      <h2>{t('Project roadmap')}</h2>
      <p>{t('Project phases and delivery milestones · {range}', { range })}</p>
      <div className="cp-gantt">
        <div className="cp-g-axis">
          {ticks.map((d, i) => (
            <span key={d} style={{ left: pct(d), transform: i === 0 ? 'none' : i === ticks.length - 1 ? 'translateX(-100%)' : undefined }}>{shortDate(lang, d)}</span>
          ))}
        </div>
        <div className="cp-g-body">
          <div className="cp-g-ov">
            {ticks.map((d) => <i key={d} className="cp-g-grid" style={{ left: pct(d) }} />)}
            <div className="cp-g-today" style={{ left: pct(today) }}><em>{t('Today · {date}', { date: shortDate(lang, today) })}</em></div>
          </div>
          {milestones.map((m, i) => {
            const status = MILESTONE_STATUS[m.state];
            const from = i === 0 ? startIso : milestones[i - 1].dueDate;
            const reached = m.state === 'done' || m.dueDate < today;
            const left = day(from) - start;
            const width = Math.max(day(m.dueDate) - day(from), 1);
            const bad = m.state === 'late' || m.state === 'revised';
            return (
              <div className="cp-g-row" key={m.id}>
                <div className="cp-g-label">
                  <b>{m.name}</b>
                  <span>{t(status.label)}</span>
                </div>
                <div className="cp-g-track">
                  <div className="cp-g-bar" style={{ left: `${(left / span) * 100}%`, width: `${(width / span) * 100}%` }}>
                    <i style={{ width: `${m.progress ?? 0}%` }} />
                  </div>
                  <span className={`cp-g-dia${reached ? ' cp-on' : ''}`} style={{ left: pct(m.dueDate) }} />
                  <div className="cp-g-note" style={{ left: pct(m.dueDate) }}>
                    <b>{m.name}</b>
                    <span className={bad ? 'cp-bad' : undefined}>
                      {shortDate(lang, m.dueDate)}{bad ? ` · ${t(status.label)}` : ''}
                    </span>
                    {m.requestedDate && <span>{t('New date requested: {date}', { date: longDate(lang, m.requestedDate) })}</span>}
                    {m.changeRequestRef && (m.state === 'late' || m.state === 'revised' || m.state === 'in_progress') && (
                      <Link to={pp.changeRequests(project.id)}>{t('See the change request ({ref})', { ref: m.changeRequestRef })}</Link>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="cp-g-legend">
          <span><i className="cp-sq" />{t('Completed share')}</span>
          <span><i className="cp-sq cp-rest" />{t('Remaining work')}</span>
          <span><i className="cp-dm cp-on" />{t('Milestone reached')}</span>
          <span><i className="cp-dm" />{t('Milestone ahead')}</span>
          <span><i className="cp-tl" />{t('Today')}</span>
        </div>
        <p className="cp-g-foot">{t('Phase bars show duration. Diamonds mark milestone due dates.')}</p>
      </div>
      <p className="cp-small" style={{ marginTop: 12 }}>
        {manager
          ? t('Where your project stands, in date order · shared by {name}, {role}', { name: manager.name, role: t(manager.role) })
          : t('Where your project stands, in date order')}
      </p>
    </section>

    {!!milestones.length && (
      <section aria-label={t('Milestones')}>
        <div className="cp-mcards">
          {milestones.map((m) => (
            <MilestoneCard
              key={m.id}
              code={m.code}
              name={m.name}
              tone={MILESTONE_BADGE[m.state].tone}
              badge={t(MILESTONE_BADGE[m.state].label)}
              meta={cardMeta(m)}
              progress={m.progress ?? 0}
            />
          ))}
        </div>
        <div className="cp-mcards">
          <Kpi
            label={t('Open change requests')}
            value={openCrs.length}
            hint={t('{n} awaiting a published decision', { n: awaiting })}
          />
        </div>
        {project.publishedOn && manager && (
          <p className="cp-small" style={{ marginTop: 12 }}>
            {t('Published {date} · {name}, {role}', { date: paddedDate(lang, project.publishedOn), name: manager.name, role: t(manager.role) })}
          </p>
        )}
      </section>
    )}
    </>
  );
}
