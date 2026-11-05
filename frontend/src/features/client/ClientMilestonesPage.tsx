import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { longDate, shortDate } from './format';
import { useProjectContext } from './ClientProjectLayout';
import type { ClientMilestone } from './types';
import { Bar } from './ui';

// The curve, node slots and "today" marker are fixed by the design (a 1160x520 canvas with two milestones).
const SLOTS = [
  { x: 330, y: 244, left: 311, top: 10 },
  { x: 850, y: 244, left: 831, top: 66 },
] as const;
const TODAY = { x: 473.75, y: 309 };
const BEFORE_TODAY = 'M0 374C170 374 190 244 330 244C395 244 432.5 276.5 473.75 309';
const AFTER_TODAY = 'M473.75 309C522 348 572 374 640 374C752 374 752 244 850 244C952 244 1052 270 1160 294';
const DASH = { stroke: '#7D879C', strokeWidth: 3, strokeDasharray: '7 7' };
const SOLID = { stroke: '#124F94', strokeWidth: 4, strokeLinecap: 'round' as const };

const STATUS_LINE = {
  done: { label: 'Completed', color: 'var(--green)', weight: 600 },
  late: { label: 'Running late', color: 'var(--red)', weight: 600 },
  in_progress: { label: 'In progress', color: 'var(--navy)', weight: 600 },
  planned: { label: 'Not started yet', color: 'var(--mute)', weight: 500 },
} as const;

function Node({ m, n, x, y }: { m: ClientMilestone; n: number; x: number; y: number }) {
  if (m.state === 'planned') {
    return (
      <>
        <circle cx={x} cy={y} r="18" fill="#fff" stroke="#7D879C" strokeWidth="2.5" strokeDasharray="3 4" />
        <text x={x} y={y + 6} textAnchor="middle" fill="#5C6178" fontSize="16" fontWeight="500" fontFamily="Inter,sans-serif">{n}</text>
      </>
    );
  }
  return (
    <>
      <circle cx={x} cy={y} r="19" fill={m.state === 'late' ? '#C94A32' : '#124F94'} />
      <text x={x} y={y + 6} textAnchor="middle" fill="#fff" fontSize="16" fontWeight="600" fontFamily="Inter,sans-serif">{n}</text>
    </>
  );
}

export function ClientMilestonesPage() {
  const { project, today } = useProjectContext();
  const { t, lang } = usePrefs();

  const milestones = [...project.milestones].sort((a, b) => a.dueDate.localeCompare(b.dueDate)).slice(0, SLOTS.length);
  const passed = milestones.filter((m) => m.state === 'done' || m.dueDate < today).length;
  const manager = project.publishedBy;

  return (
    <>
      <h2 className="cp-sec" style={{ fontSize: 20, marginTop: 32, fontWeight: 600 }}>{t('Milestones')}</h2>
      <p className="cp-sub" style={{ marginTop: 0 }}>
        {t('Where your project stands, in date order · shared by {name}, {role}', { name: manager.name, role: t(manager.role) })}
      </p>
      <div className="cp-msv">
        <svg width="1160" height="520" viewBox="0 0 1160 520" fill="none" aria-hidden="true">
          <path d={BEFORE_TODAY} {...(passed >= 1 ? SOLID : DASH)} />
          <path d={AFTER_TODAY} {...(passed >= 2 ? SOLID : DASH)} />
          {milestones.map((m, i) => (
            <Node key={m.id} m={m} n={i + 1} x={SLOTS[i].x} y={SLOTS[i].y} />
          ))}
          {passed === 1 && <circle cx={TODAY.x} cy={TODAY.y} r="7.5" fill="#0D1240" stroke="#fff" strokeWidth="3" />}
        </svg>
        {milestones.map((m, i) => {
          const status = STATUS_LINE[m.state];
          const open = m.state === 'late' || m.state === 'in_progress';
          return (
            <div className="cp-blk" key={m.id} style={{ left: SLOTS[i].left, top: SLOTS[i].top }}>
              <h5>{m.name}</h5>
              <div className="cp-st" style={{ color: status.color, fontWeight: status.weight }}>{t(status.label)}</div>
              <div className="cp-t">
                {m.state === 'planned'
                  ? t('Planned for {date}', { date: longDate(lang, m.dueDate) })
                  : m.state === 'done'
                    ? t('Completed on {date}', { date: longDate(lang, m.dueDate) })
                    : t('Was due {date}', { date: longDate(lang, m.dueDate) })}
              </div>
              {m.requestedDate && (
                <div className="cp-t" style={{ marginTop: 12 }}>
                  {t('New date requested: {date}', { date: longDate(lang, m.requestedDate) })}
                </div>
              )}
              <div className="cp-pc2">{t('{n}% complete', { n: m.progress })}</div>
              <Bar value={m.progress} style={{ width: 300, height: 8 }} />
              {open && m.changeRequestRef && (
                <div style={{ marginTop: 10, fontSize: 14 }}>
                  <Link to={paths.clientChangeRequests(project.id)}>
                    {t('See the change request ({ref})', { ref: m.changeRequestRef })}
                  </Link>
                </div>
              )}
            </div>
          );
        })}
        {passed === 1 && (
          <div className="cp-today" style={{ left: 416, top: 324 }}>{t('Today · {date}', { date: shortDate(lang, today) })}</div>
        )}
        <div className="cp-lg">
          <span>{t('Done so far')}</span>
          <span className="cp-d">{t('Still ahead')}</span>
        </div>
      </div>
    </>
  );
}
