import { useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf, longDate, shortDate } from '@/features/client/format';
import './manager.css';

type Tone = 'ok' | 'warn' | 'over';
interface Engagement { name: string; role: string; project: string; pct: number; through: string; free: string; start: number; end: number }
interface Load { name: string; project: string; projects: number; open: number; overdue: number; effort: number | null; unestimated?: number }

const AS_OF = '2026-11-17';
// Twelve month columns starting Nov 2026, labelled in the page language ("Nov 26" / "Nov 26").
const monthLabels = (lang: string) =>
  Array.from({ length: 12 }, (_, i) =>
    new Date(Date.UTC(2026, 10 + i, 1))
      .toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', { timeZone: 'UTC', month: 'short', year: '2-digit' })
      .replace('.', ''));
const num = (lang: string, n: number) => n.toLocaleString(lang === 'de' ? 'de-DE' : 'en-GB');
// Stable per-person avatar colour (hue from the name) so the same person looks the same on both tabs.
const avatarStyle = (name: string) => {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return { background: `hsl(${h} 45% 32%)`, color: '#fff' };
};
const toneOf = (pct: number): Tone => (pct > 100 ? 'over' : pct >= 80 ? 'warn' : 'ok');

// The backend has no team endpoint yet: sample data until the API exists. start/end are month-column offsets.
const ENGAGEMENTS: Engagement[] = [
  { name: 'Mia Chen', role: 'Developer', project: 'AI Operations Rollout', pct: 85, through: '2026-11-17', free: '2026-11-18', start: 0, end: 0.5 },
  { name: 'Jon Doe', role: 'Developer', project: 'Website Development', pct: 100, through: '2026-11-17', free: '2026-11-18', start: 0, end: 0.5 },
  { name: 'Noah Patel', role: 'Developer', project: 'Website Development', pct: 100, through: '2026-12-20', free: '2026-12-21', start: 0, end: 1.8 },
  { name: 'Sofia Lee', role: 'Developer', project: 'Website Development', pct: 100, through: '2026-12-20', free: '2026-12-21', start: 0, end: 1.8 },
  { name: 'Eli Reed', role: 'QA Engineer', project: 'AI Operations Rollout', pct: 85, through: '2026-11-17', free: '2026-11-18', start: 0, end: 0.5 },
  { name: 'Avery Cole', role: 'Designer', project: 'AI Operations Rollout', pct: 100, through: '2026-11-17', free: '2026-11-18', start: 0, end: 0.5 },
];

const LOADS: Load[] = [
  { name: 'Lind Geci', project: 'BRECO', projects: 1, open: 27, overdue: 27, effort: 58.5, unestimated: 6 },
  { name: 'Florent Sahiti', project: 'BRECO', projects: 1, open: 10, overdue: 10, effort: 25.5, unestimated: 1 },
  { name: 'Adea Piperku', project: 'EOWE', projects: 1, open: 5, overdue: 5, effort: 8.2 },
  { name: 'Lum Meta', project: 'EOWE', projects: 1, open: 5, overdue: 5, effort: 7.8 },
  { name: 'Arbios Kastrati', project: 'EOWE', projects: 1, open: 3, overdue: 3, effort: 0.7 },
  { name: 'Rina Dermaku', project: 'Borek PM Hub', projects: 1, open: 19, overdue: 16, effort: null },
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
  const { t, lang } = usePrefs();
  return (
    <>
      <div className="mg-stats mg-stats-2">
        <Stat label={t('Free today')} value="2" note={t('People with no allocation today')} tone="mg-ok" />
        <Stat label={t('Free within 3 months')} value="8" note={t('Includes people free today')} />
      </div>
      <section className="mg-panel">
        <div className="mg-panel-head">
          <div><h3>{t('Planned engagements')}</h3><p>{t('Project allocations by person')}</p></div>
          <span className="mg-small">{t('As of')} {longDate(lang, AS_OF)}</span>
        </div>
        <ul className="mg-legend">
          <li><i className="mg-dot mg-okbg" />{t('Below 80% · Capacity available')}</li>
          <li><i className="mg-dot mg-warn" />{t('80-100% · At or near capacity')}</li>
          <li><i className="mg-dot mg-over" />{t('Over 100% · Overallocated')}</li>
        </ul>
        <div className="mg-cap mg-cap-h">
          <span>{t('Team member')}</span>
          <div className="mg-months">{monthLabels(lang).map((m) => <span key={m}>{m}</span>)}</div>
        </div>
        {ENGAGEMENTS.map((e) => (
          <div className="mg-cap" key={e.name}>
            <div className="mg-who mg-row-who">
              <span className="mg-ini" style={avatarStyle(e.name)} aria-hidden="true">{initialsOf(e.name)}</span>
              <div>
                <h3>{e.name}</h3>
                <p>{t(e.role)}</p>
                <p className="mg-ok">{t('No allocation planned from')} {shortDate(lang, e.free)}</p>
              </div>
            </div>
            <div className="mg-track">
              <span className="mg-eng-label">{e.project} · {e.pct}% · {t('through')} {shortDate(lang, e.through)}</span>
              <i className={`mg-bar mg-${toneOf(e.pct)}`} style={{ left: `${(e.start / 12) * 100}%`, width: `${((e.end - e.start) / 12) * 100}%` }} />
            </div>
          </div>
        ))}
      </section>
    </>
  );
}

function Workload() {
  const { t, lang } = usePrefs();
  const max = Math.max(...LOADS.map((l) => l.effort ?? 0));
  return (
    <>
      <div className="mg-stats">
        <Stat label={t('People with open work')} value="8" note={t('Across {n} projects', { n: 4 })} />
        <Stat label={t('Open tasks')} value="71" note={t('Most: {name} · {n}', { name: 'Lind Geci', n: 27 })} />
        <Stat label={t('Overdue tasks')} value="68" note={t('Past their due date')} tone="mg-over-t" />
        <Stat label={t('Remaining effort')} value={`${num(lang, 100.7)} ${t('PD')}`} note={t('{n} tasks not estimated', { n: 28 })} />
      </div>
      <section className="mg-panel">
        <h3>{t('Load per person')}</h3>
        <p className="mg-small">{t('Highest remaining effort first · Bars compare with the highest estimated load.')}</p>
        <div className="mg-load mg-load-h">
          <span>{t('Person / project')}</span><span>{t('Open')}</span><span>{t('Overdue')}</span><span>{t('Remaining effort')}</span><span>{t('Share of highest load')}</span>
        </div>
        {LOADS.map((l) => (
          <div className="mg-load" key={l.name}>
            <div className="mg-who mg-row-who">
              <span className="mg-ini" style={avatarStyle(l.name)} aria-hidden="true">{initialsOf(l.name)}</span>
              <div><h3>{l.name}</h3><p>{l.project} · {t(l.projects === 1 ? '{n} project' : '{n} projects', { n: l.projects })}</p></div>
            </div>
            <span>{l.open}</span>
            <span className="mg-over-t">{l.overdue}</span>
            <div>
              {l.effort === null ? <b className="mg-warn-t">{t('Not estimated')}</b> : <b>{num(lang, l.effort)} {t('PD')}</b>}
              {!!l.unestimated && <p className="mg-small">+ {t('{n} tasks not estimated', { n: l.unestimated })}</p>}
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
