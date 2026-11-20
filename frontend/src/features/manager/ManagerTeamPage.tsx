import { useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from '@/features/client/format';
import './manager.css';

type Tone = 'ok' | 'warn' | 'over';
interface Engagement { name: string; role: string; project: string; pct: number; through: string; free: string; start: number; end: number }
interface Load { name: string; project: string; open: number; overdue: number; effort: number | null; unestimated?: number }

const MONTHS = ['Nov 26', 'Dec 26', 'Jan 27', 'Feb 27', 'Mar 27', 'Apr 27', 'May 27', 'Jun 27', 'Jul 27', 'Aug 27', 'Sep 27', 'Oct 27'];
const toneOf = (pct: number): Tone => (pct > 100 ? 'over' : pct >= 80 ? 'warn' : 'ok');

// The backend has no team endpoint yet: sample data until the API exists. start/end are month-column offsets.
const ENGAGEMENTS: Engagement[] = [
  { name: 'Mia Chen', role: 'Developer', project: 'AI Operations Rollout', pct: 85, through: '17 Nov', free: '18 Nov', start: 0, end: 0.5 },
  { name: 'Jon Doe', role: 'Developer', project: 'Website Development', pct: 100, through: '17 Nov', free: '18 Nov', start: 0, end: 0.5 },
  { name: 'Noah Patel', role: 'Developer', project: 'Website Development', pct: 100, through: '20 Dec', free: '21 Dec', start: 0, end: 1.8 },
  { name: 'Sofia Lee', role: 'Developer', project: 'Website Development', pct: 100, through: '20 Dec', free: '21 Dec', start: 0, end: 1.8 },
  { name: 'Eli Reed', role: 'QA Engineer', project: 'AI Operations Rollout', pct: 85, through: '17 Nov', free: '18 Nov', start: 0, end: 0.5 },
  { name: 'Avery Cole', role: 'Designer', project: 'AI Operations Rollout', pct: 100, through: '17 Nov', free: '18 Nov', start: 0, end: 0.5 },
];

const LOADS: Load[] = [
  { name: 'Lind Geci', project: 'BRECO · 1 project', open: 27, overdue: 27, effort: 58.5, unestimated: 6 },
  { name: 'Florent Sahiti', project: 'BRECO · 1 project', open: 10, overdue: 10, effort: 25.5, unestimated: 1 },
  { name: 'Adea Piperku', project: 'EOWE · 1 project', open: 5, overdue: 5, effort: 8.2 },
  { name: 'Lum Meta', project: 'EOWE · 1 project', open: 5, overdue: 5, effort: 7.8 },
  { name: 'Arbios Kastrati', project: 'EOWE · 1 project', open: 3, overdue: 3, effort: 0.7 },
  { name: 'Rina Dermaku', project: 'Borek PM Hub · 1 project', open: 19, overdue: 16, effort: null },
];

/** Team screen (borek_screens.html): Capacity timeline and Workload per person. */
export function ManagerTeamPage() {
  const { t } = usePrefs();
  const [tab, setTab] = useState<'capacity' | 'workload'>('capacity');
  return (
    <div className="mg-team">
      <h2 className="cp-section-title">{t(tab === 'capacity' ? 'Team Capacity' : 'Team workload')}</h2>
      <p className="cp-section-sub">
        {t(tab === 'capacity'
          ? 'See where people are engaged and when they become available.'
          : 'Open tasks and remaining effort per person, across all projects.')}
      </p>
      <div className="mg-tabs" role="tablist">
        {(['capacity', 'workload'] as const).map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'on' : undefined} onClick={() => setTab(k)}>
            {t(k === 'capacity' ? 'Capacity' : 'Workload')}
          </button>
        ))}
      </div>
      {tab === 'capacity' ? <Capacity /> : <Workload />}
    </div>
  );
}

function Stat({ label, value, note, tone }: { label: string; value: string; note: string; tone?: string }) {
  return (
    <div className="mg-stat"><span>{label}</span><strong className={tone}>{value}</strong><small>{note}</small></div>
  );
}

function Capacity() {
  const { t } = usePrefs();
  return (
    <>
      <div className="mg-stats mg-stats-2">
        <Stat label={t('Free today')} value="2" note={t('People with no allocation today')} tone="mg-ok" />
        <Stat label={t('Free within 3 months')} value="8" note={t('Includes people free today')} />
      </div>
      <section className="mg-panel">
        <div className="mg-panel-head">
          <div><h3>{t('Planned engagements')}</h3><p>{t('Project allocations by person')}</p></div>
          <span className="mg-small">{t('As of')} 17 Nov 2026</span>
        </div>
        <ul className="mg-legend">
          <li><i className="mg-dot mg-okbg" />{t('Below 80% · Capacity available')}</li>
          <li><i className="mg-dot mg-warn" />{t('80-100% · At or near capacity')}</li>
          <li><i className="mg-dot mg-over" />{t('Over 100% · Overallocated')}</li>
        </ul>
        <div className="mg-cap mg-cap-h">
          <span>{t('TEAM MEMBER')}</span>
          <div className="mg-months">{MONTHS.map((m) => <span key={m}>{m}</span>)}</div>
        </div>
        {ENGAGEMENTS.map((e) => (
          <div className="mg-cap" key={e.name}>
            <div className="mg-who mg-row-who">
              <span className="mg-ini" aria-hidden="true">{initialsOf(e.name)}</span>
              <div>
                <h3>{e.name}</h3>
                <p>{t(e.role)}</p>
                <p className="mg-ok">{t('No allocation planned from')} {e.free}</p>
              </div>
            </div>
            <div className="mg-track">
              <span className="mg-eng-label">{e.project} · {e.pct}% · {t('through')} {e.through}</span>
              <i className={`mg-bar mg-${toneOf(e.pct)}`} style={{ left: `${(e.start / 12) * 100}%`, width: `${((e.end - e.start) / 12) * 100}%` }} />
            </div>
          </div>
        ))}
      </section>
    </>
  );
}

function Workload() {
  const { t } = usePrefs();
  const max = Math.max(...LOADS.map((l) => l.effort ?? 0));
  return (
    <>
      <div className="mg-stats">
        <Stat label={t('People with open work')} value="8" note={t('Across 4 projects')} />
        <Stat label={t('Open tasks')} value="71" note={t('Most: Lind Geci · 27')} />
        <Stat label={t('Overdue tasks')} value="68" note={t('Past their due date')} tone="mg-over-t" />
        <Stat label={t('Remaining effort')} value="100.7 PD" note={t('28 tasks not estimated')} />
      </div>
      <section className="mg-panel">
        <h3>{t('Load per person')}</h3>
        <p className="mg-small">{t('Highest remaining effort first · Bars compare with the highest estimated load.')}</p>
        <div className="mg-load mg-load-h">
          <span>{t('PERSON / PROJECT')}</span><span>{t('OPEN')}</span><span>{t('OVERDUE')}</span><span>{t('REMAINING EFFORT')}</span><span>{t('SHARE OF HIGHEST LOAD')}</span>
        </div>
        {LOADS.map((l) => (
          <div className="mg-load" key={l.name}>
            <div className="mg-who mg-row-who">
              <span className="mg-ini" aria-hidden="true">{initialsOf(l.name)}</span>
              <div><h3>{l.name}</h3><p>{l.project}</p></div>
            </div>
            <span>{l.open}</span>
            <span className="mg-over-t">{l.overdue}</span>
            <div>
              {l.effort === null ? <b className="mg-warn-t">{t('Not estimated')}</b> : <b>{l.effort} PD</b>}
              {!!l.unestimated && <p className="mg-small">+ {l.unestimated} {t('tasks not estimated')}</p>}
            </div>
            <div className="mg-share">
              {l.effort === null ? <small>{t('No estimate available')}</small> : <i style={{ width: `${(l.effort / max) * 100}%` }} />}
            </div>
          </div>
        ))}
      </section>
    </>
  );
}
