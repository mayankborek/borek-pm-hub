import { useEffect, useRef, useState } from 'react';
import highestIcon from '@/features/projects/assets/priority-highest.svg';
import highIcon from '@/features/projects/assets/priority-high.svg';
import mediumIcon from '@/features/projects/assets/priority-medium.svg';
import lowIcon from '@/features/projects/assets/priority-low.svg';
import type { TaskPriority } from './tasksApi';

/** The app has four levels; Critical takes the design's "Highest" icon. */
export const PRIORITY_OPTIONS: { value: TaskPriority; label: string; icon: string }[] = [
  { value: 'critical', label: 'Critical', icon: highestIcon },
  { value: 'high', label: 'High', icon: highIcon },
  { value: 'medium', label: 'Medium', icon: mediumIcon },
  { value: 'low', label: 'Low', icon: lowIcon },
];

/** Icon + label (Figma "PriorityIndicator · V1"), for menus and forms. */
export function PriorityIndicator({ priority }: { priority: TaskPriority }) {
  const p = PRIORITY_OPTIONS.find((o) => o.value === priority) ?? PRIORITY_OPTIONS[2];
  return (
    <span className="pi">
      <span className="pi-icon">
        <img src={p.icon} alt="" width={16} height={16} />
      </span>
      {p.label}
    </span>
  );
}

/** Priority dropdown (Figma "Priority selector · V1"): selected priority on top, options listed below with the current one highlighted. */
export function PrioritySelect({ value, onChange }: { value: TaskPriority; onChange: (p: TaskPriority) => void }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, [open]);

  const openList = () => {
    setActive(Math.max(0, PRIORITY_OPTIONS.findIndex((o) => o.value === value)));
    setOpen(true);
  };
  const choose = (p: TaskPriority) => {
    setOpen(false);
    if (p !== value) onChange(p);
    root.current?.querySelector('button')?.focus();
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    const n = PRIORITY_OPTIONS.length;
    if (e.key === 'Escape' && open) {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) return openList();
      setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : -1) + n) % n);
    } else if ((e.key === 'Enter' || e.key === ' ') && open) {
      e.preventDefault();
      choose(PRIORITY_OPTIONS[active].value);
    }
  };

  return (
    <div className="ps" ref={root} onKeyDown={onKeyDown}>
      <button type="button" className={open ? 'ps-btn open' : 'ps-btn'} aria-haspopup="listbox" aria-expanded={open} aria-label="Priority" onClick={() => (open ? setOpen(false) : openList())}>
        <PriorityIndicator priority={value} />
      </button>
      {open && (
        <ul className="ps-list" role="listbox" aria-label="Priority">
          {PRIORITY_OPTIONS.map((o, i) => (
            <li key={o.value} role="option" aria-selected={o.value === value} className={i === active ? 'active' : undefined} onMouseEnter={() => setActive(i)} onClick={() => choose(o.value)}>
              <PriorityIndicator priority={o.value} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
