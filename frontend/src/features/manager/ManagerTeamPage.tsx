import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from '@/features/client/format';
import './manager.css';

type Load = 'free' | 'busy' | 'over';
interface Member { name: string; role: string; project: string; loads: Load[] }

const WEEKS = Array.from({ length: 12 }, (_, i) => `W${i + 1}`);
const o = (...n: number[]): Load[] => n.map((v) => (v === 0 ? 'free' : v === 1 ? 'busy' : 'over'));

// The backend has no team endpoint yet: sample data until the API exists.
const MEMBERS: Member[] = [
  { name: 'Priya Nair', role: 'Frontend developer', project: 'Website Development', loads: o(1, 1, 1, 1, 1, 2, 1, 1, 0, 0, 0, 0) },
  { name: 'Daniel Weber', role: 'Backend developer', project: 'Customer portal', loads: o(1, 1, 2, 2, 1, 1, 1, 1, 1, 0, 0, 0) },
  { name: 'Sofia Rossi', role: 'UX designer', project: 'Customer portal', loads: o(1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0, 0) },
  { name: 'Liam Becker', role: 'QA engineer', project: 'Website Development', loads: o(0, 0, 1, 1, 1, 1, 1, 2, 2, 1, 1, 0) },
  { name: 'Aisha Khan', role: 'DevOps engineer', project: 'Customer portal', loads: o(1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1) },
];

/** Team tab (borek_screens.html): capacity summary and a 12-week workload planner per team member. */
export function ManagerTeamPage() {
  const { t } = usePrefs();
  const free = MEMBERS.filter((m) => m.loads[0] === 'free').length;
  const label: Record<Load, string> = { free: t('Available'), busy: t('Allocated'), over: t('Over capacity') };

  return (
    <>
      <h2 className="cp-section-title">{t('Team workload')}</h2>
      <p className="cp-section-sub">{t('Capacity across your delivery team for the next 12 weeks.')}</p>
      <div className="mg-stats">
        <div className="mg-stat"><span>{t('Available this week')}</span><strong className="mg-ok">{free}</strong></div>
        <div className="mg-stat"><span>{t('Team members')}</span><strong>{MEMBERS.length}</strong></div>
      </div>
      <section className="mg-plan" aria-label={t('Workload planner')}>
        <div className="mg-plan-head">
          <h3>{t('Workload planner')}</h3>
          <ul className="mg-legend">
            {(['free', 'busy', 'over'] as Load[]).map((k) => <li key={k}><i className={`mg-dot mg-${k}`} />{label[k]}</li>)}
          </ul>
        </div>
        <div className="mg-grid mg-grid-h">
          <span />
          {WEEKS.map((w) => <span key={w}>{w}</span>)}
        </div>
        {MEMBERS.map((m) => (
          <div className="mg-grid" key={m.name}>
            <div className="mg-who mg-row-who">
              <span className="mg-ini" aria-hidden="true">{initialsOf(m.name)}</span>
              <div><h3>{m.name}</h3><p>{t(m.role)} · {m.project}</p></div>
            </div>
            {m.loads.map((l, i) => <span key={i} className={`mg-cell mg-${l}`} title={`${WEEKS[i]}: ${label[l]}`} />)}
          </div>
        ))}
      </section>
    </>
  );
}
