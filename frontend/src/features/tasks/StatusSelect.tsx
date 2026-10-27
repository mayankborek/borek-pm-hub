import { useEffect, useRef, useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import type { StatusCategory } from './tasksApi';

interface Option {
  id: string;
  name: string;
  category: StatusCategory;
}

/** Named workflow states keep their own colour; anything else follows its category (Figma "Filter option · Status"). */
const NAME_TONE: Record<string, string> = { 'code review': 'review', testing: 'testing' };
export const toneOf = (o: Option) => NAME_TONE[o.name.toLowerCase()] ?? o.category;

/** Single-select status dropdown whose options are the coloured status labels from the Board filter popover. */
export function StatusSelect({ value, options, onChange }: { value: string; options: Option[]; onChange: (id: string) => void }) {
  const { t } = usePrefs();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const current = options.find((o) => o.id === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, [open]);

  const openList = () => {
    setActive(Math.max(0, options.findIndex((o) => o.id === value)));
    setOpen(true);
  };
  const choose = (o: Option) => {
    setOpen(false);
    if (o.id !== value) onChange(o.id);
    root.current?.querySelector('button')?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && open) {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) return openList();
      setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length);
    } else if ((e.key === 'Enter' || e.key === ' ') && open) {
      e.preventDefault();
      choose(options[active]);
    }
  };

  if (!current) return null;
  return (
    <div className="ss" ref={root} onKeyDown={onKeyDown}>
      <button type="button" className="ss-btn" aria-haspopup="listbox" aria-expanded={open} aria-label={`${t('Status')}: ${t(current.name)}`} onClick={() => (open ? setOpen(false) : openList())}>
        <span className={`ss-label tone-${toneOf(current)}`}>{t(current.name)}</span>
        <span aria-hidden="true" className="ss-chev">
          ⌄
        </span>
      </button>
      {open && (
        <ul className="ss-list" role="listbox" aria-label={t('Status')}>
          {options.map((o, i) => (
            <li key={o.id} role="option" aria-selected={o.id === value} className={i === active ? 'active' : undefined} onMouseEnter={() => setActive(i)} onClick={() => choose(o)}>
              <span className={`ss-label tone-${toneOf(o)}`}>{t(o.name)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
