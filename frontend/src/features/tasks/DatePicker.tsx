import { useEffect, useRef, useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';

interface Props {
  label: string;
  value: string | null;
  onChange: (value: string | null) => void;
  /** Earliest allowed date (due date must be on or after the start date). */
  min?: string | null;
  /** Latest allowed date (start date must be on or before the due date). */
  max?: string | null;
  hint: string;
  /** Shown when a date outside the allowed range is chosen. */
  error: string;
}

type Lang = 'en' | 'de';
const monthName = (lang: Lang, m: number, style: 'long' | 'short') => {
  const long = new Date(2000, m, 1).toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', { month: 'long' });
  return style === 'long' || lang === 'de' ? (style === 'long' ? long : long.slice(0, 3)) : long.slice(0, 3);
};
const WEEKDAYS: Record<Lang, string[]> = { en: ['M', 'T', 'W', 'T', 'F', 'S', 'S'], de: ['M', 'D', 'M', 'D', 'F', 'S', 'S'] };

const pad = (n: number) => String(n).padStart(2, '0');
const iso = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;
const parse = (v: string) => {
  const [y, m, d] = v.split('-').map(Number);
  return { y, m: m - 1, d };
};
const show = (v: string, lang: Lang) => {
  const { y, m, d } = parse(v);
  return `${pad(d)} ${monthName(lang, m, 'short')} ${y}`;
};

/** Calendar popover from Figma "Field picker · PM · Start date" (Monday-first, hairline panel, Close link). */
export function DatePicker({ label, value, onChange, min, max, hint, error }: Props) {
  const { t, lang } = usePrefs();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => {
    const { y, m } = parse(value ?? iso(new Date().getFullYear(), new Date().getMonth(), 1));
    return { y, m };
  });
  const [rejected, setRejected] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  const toggle = () => {
    if (!open) {
      const { y, m } = parse(value ?? iso(new Date().getFullYear(), new Date().getMonth(), 1));
      setView({ y, m });
    }
    setRejected(false);
    setOpen(!open);
  };

  const step = (by: number) => {
    const total = view.y * 12 + view.m + by;
    setView({ y: Math.floor(total / 12), m: total % 12 });
  };

  const lead = (new Date(view.y, view.m, 1).getDay() + 6) % 7; // Monday = 0
  const days = new Date(view.y, view.m + 1, 0).getDate();
  const cells: (number | null)[] = [...Array<null>(lead).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  const blocked = (d: string) => (!!min && d < min) || (!!max && d > max);

  return (
    <div className="dp" ref={root}>
      <button type="button" className={`dp-btn${open ? ' open' : ''}`} aria-label={t(label)} aria-haspopup="dialog" aria-expanded={open} onClick={toggle}>
        {value ? show(value, lang) : t('Not set')}
      </button>
      {open && (
        <div className="dp-pop" role="dialog" aria-label={`${t(label)}, ${monthName(lang, view.m, 'long')} ${view.y}`}>
          <div className="dp-head">
            <button type="button" aria-label={t('Previous month')} onClick={() => step(-1)}>‹</button>
            <span aria-live="polite">{monthName(lang, view.m, 'long')} {view.y}</span>
            <button type="button" aria-label={t('Next month')} onClick={() => step(1)}>›</button>
          </div>
          <div className="dp-grid dp-week" aria-hidden="true">
            {WEEKDAYS[lang].map((d, i) => (
              <span key={i}>{d}</span>
            ))}
          </div>
          <div className="dp-grid">
            {cells.map((d, i) => {
              if (d === null) return <span key={i} />;
              const v = iso(view.y, view.m, d);
              return (
                <button
                  key={i}
                  type="button"
                  className={v === value ? 'sel' : ''}
                  aria-label={t('Choose {date}', { date: `${d} ${monthName(lang, view.m, 'short')} ${view.y}` })}
                  aria-pressed={v === value}
                  aria-disabled={blocked(v)}
                  onClick={() => {
                    if (blocked(v)) return setRejected(true);
                    onChange(v);
                    setOpen(false);
                  }}
                >
                  {d}
                </button>
              );
            })}
          </div>
          <p className="dp-hint">{t(hint)}</p>
          <p className="dp-error" role="alert">{rejected ? t(error) : ''}</p>
          <div className="dp-foot">
            <button type="button" onClick={() => setOpen(false)}>{t('Close')}</button>
            {value && (
              <button type="button" className="dp-clear" onClick={() => { onChange(null); setOpen(false); }}>
                {t('Clear')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
