import { useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf, longDate, shortDate } from '@/features/client/format';
import { PortalPending } from '@/features/client/ui';
import { useCapacity, useWorkload, type CapacityStatus, type PersonCapacity, type Segment, type WorkloadPerson } from './teamApi';
import './manager.css';

type Tone = 'ok' | 'warn' | 'over';
type T = (key: string, vars?: Record<string, string | number>) => string;

const MONTHS = 12;
const num = (lang: string, n: number) => n.toLocaleString(lang === 'de' ? 'de-DE' : 'en-GB');
// Stable per-person avatar colour (hue from the name) so the same person looks the same on both tabs.
const avatarStyle = (name: string) => {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return { background: `hsl(${h} 45% 32%)`, color: '#fff' };
};
const TONE: Partial<Record<CapacityStatus, Tone>> = { available: 'ok', near_capacity: 'warn', overallocated: 'over', conflict: 'over' };

/** The timeline starts in the month the capacity period begins in. */
interface Origin { y: number; m: number }
const originOf = (iso: string): Origin => ({ y: Number(iso.slice(0, 4)), m: Number(iso.slice(5, 7)) - 1 });
/** Position along the twelve equal month columns, 0 to 1: whole months plus the share of the month gone. */
function position(iso: string, origin: Origin) {
  const y = Number(iso.slice(0, 4));
  const m = Number(iso.slice(5, 7)) - 1;
  const day = Number(iso.slice(8, 10));
  const days = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  return ((y - origin.y) * 12 + (m - origin.m) + (day - 1) / days) / MONTHS;
}
const nextDay = (iso: string) => new Date(Date.parse(`${iso}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10);
const booked = (s: Segment) => s.reserved_hours > 0 && s.status !== 'unavailable';

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
  const query = useCapacity();
  const { data } = query;
  if (!data) return <PortalPending query={query} />;

  const origin = originOf(data.today);
  const months = Array.from({ length: MONTHS }, (_, i) =>
    new Date(Date.UTC(origin.y, origin.m + i, 1))
      .toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', { timeZone: 'UTC', month: 'short', year: '2-digit' })
      .replace('.', ''));

  return (
    <>
      <div className="mg-stats mg-stats-2">
        <Stat label={t('Free today')} value={String(data.summary.free_today)} note={t('People with no allocation today')} tone="mg-ok" />
        <Stat label={t('Free within 3 months')} value={String(data.summary.free_within_3_months)} note={t('Includes people free today')} />
      </div>
      <section className="mg-panel">
        <div className="mg-panel-head">
          <div><h3>{t('Planned engagements')}</h3><p>{t('Project allocations by person')}</p></div>
          <span className="mg-small">{t('As of')} {longDate(lang, data.today)}</span>
        </div>
        <ul className="mg-legend">
          <li><i className="mg-dot mg-okbg" />{t('Below 80% · Capacity available')}</li>
          <li><i className="mg-dot mg-warn" />{t('80-100% · At or near capacity')}</li>
          <li><i className="mg-dot mg-over" />{t('Over 100% · Overallocated')}</li>
        </ul>
        <div className="mg-cap mg-cap-h">
          <span>{t('Team member')}</span>
          <div className="mg-months">{months.map((m) => <span key={m}>{m}</span>)}</div>
        </div>
        {!data.people.length && <p className="mg-small">{t('No team members yet.')}</p>}
        {data.people.map((e) => <CapacityRow key={e.person.id} entry={e} origin={origin} />)}
      </section>
    </>
  );
}

function CapacityRow({ entry: e, origin }: { entry: PersonCapacity; origin: Origin }) {
  const { t, lang } = usePrefs();
  const segments = e.segments.filter(booked);
  const first = segments[0];
  const last = segments[segments.length - 1];
  return (
    <div className="mg-cap">
      <div className="mg-who mg-row-who">
        <span className="mg-ini" style={avatarStyle(e.person.name)} aria-hidden="true">{initialsOf(e.person.name)}</span>
        <div>
          <h3>{e.person.name}</h3>
          {e.person.job_title && <p>{t(e.person.job_title)}</p>}
          {e.next_unallocated_day && <p className="mg-ok">{t('No allocation planned from')} {shortDate(lang, e.next_unallocated_day)}</p>}
        </div>
      </div>
      <div className="mg-track">
        {first && last && (
          <span className="mg-eng-label">
            {first.projects.map((p) => p.project.name).join(', ')} · {Math.round(first.total_percent ?? 0)}% · {t('through')} {shortDate(lang, last.end)}
          </span>
        )}
        {segments.map((s) => {
          const left = Math.max(0, position(s.start, origin));
          const right = Math.min(1, position(nextDay(s.end), origin));
          if (right <= left) return null;
          return (
            <i
              key={s.start}
              className={`mg-bar mg-${TONE[s.status] ?? 'ok'}`}
              style={{ left: `${left * 100}%`, width: `${(right - left) * 100}%` }}
              title={`${s.projects.map((p) => p.project.name).join(', ')} · ${Math.round(s.total_percent ?? 0)}%`}
            />
          );
        })}
      </div>
    </div>
  );
}

/** "Client · 1 project": the client when the person works on just one project, else only the count. */
function projectLine(p: WorkloadPerson, t: T) {
  const count = t(p.projects.length === 1 ? '{n} project' : '{n} projects', { n: p.projects.length });
  const only = p.projects.length === 1 ? (p.projects[0].client ?? p.projects[0].project.name) : null;
  return only ? `${only} · ${count}` : count;
}

function Workload() {
  const { t, lang } = usePrefs();
  const query = useWorkload();
  const { data } = query;
  if (!data) return <PortalPending query={query} />;

  const { summary, people, unassigned } = data;
  const max = Math.max(0, ...people.map((l) => l.effort_pd ?? 0));
  return (
    <>
      <div className="mg-stats">
        <Stat label={t('People with open work')} value={String(summary.people_with_open_work)} note={t('Across {n} projects', { n: summary.projects_with_open_work })} />
        <Stat
          label={t('Open tasks')}
          value={String(summary.open)}
          note={summary.most_open ? t('Most: {name} · {n}', { name: summary.most_open.name, n: summary.most_open_count }) : t('Nobody has open work')}
        />
        <Stat label={t('Overdue tasks')} value={String(summary.overdue)} note={t('Past their due date')} tone="mg-over-t" />
        <Stat label={t('Remaining effort')} value={`${num(lang, summary.effort_pd)} ${t('PD')}`} note={t('{n} tasks not estimated', { n: summary.unestimated })} />
      </div>
      <section className="mg-panel">
        <h3>{t('Load per person')}</h3>
        <p className="mg-small">{t('Highest remaining effort first · Bars compare with the highest estimated load.')}</p>
        <div className="mg-load mg-load-h">
          <span>{t('Person / project')}</span><span>{t('Open')}</span><span>{t('Overdue')}</span><span>{t('Remaining effort')}</span><span>{t('Share of highest load')}</span>
        </div>
        {!people.length && <p className="mg-small">{t('Nobody has open work')}</p>}
        {people.map((l) => (
          <div className="mg-load" key={l.person.id}>
            <div className="mg-who mg-row-who">
              <span className="mg-ini" style={avatarStyle(l.person.name)} aria-hidden="true">{initialsOf(l.person.name)}</span>
              <div><h3>{l.person.name}</h3><p>{projectLine(l, t)}</p></div>
            </div>
            <span>{l.open}</span>
            <span className="mg-over-t">{l.overdue}</span>
            <div>
              {l.effort_pd === null ? <b className="mg-warn-t">{t('Not estimated')}</b> : <b>{num(lang, l.effort_pd)} {t('PD')}</b>}
              {l.unestimated > 0 && <p className="mg-small">{l.effort_pd === null ? '' : '+ '}{t('{n} tasks not estimated', { n: l.unestimated })}</p>}
            </div>
            <div className="mg-share">
              {l.effort_pd === null || max === 0 ? <small>{t('No estimate available')}</small> : <i style={{ width: `${(l.effort_pd / max) * 100}%` }} />}
            </div>
          </div>
        ))}
        {unassigned.open > 0 && (
          <div className="mg-load">
            <div className="mg-who mg-row-who">
              <span className="mg-ini" aria-hidden="true">–</span>
              <div><h3>{t('Unassigned')}</h3></div>
            </div>
            <span>{unassigned.open}</span>
            <span className="mg-over-t">{unassigned.overdue}</span>
            <div>
              {unassigned.effort_pd === null ? <b className="mg-warn-t">{t('Not estimated')}</b> : <b>{num(lang, unassigned.effort_pd)} {t('PD')}</b>}
            </div>
            <div className="mg-share" />
          </div>
        )}
      </section>
    </>
  );
}
