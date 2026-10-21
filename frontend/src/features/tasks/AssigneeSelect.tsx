import { useEffect, useRef, useState } from 'react';
import type { ProjectMember } from './tasksApi';

interface Props {
  value: string | null;
  /** Current assignee, shown even while the member list is still loading. */
  current: { id: string; name: string } | null;
  members: ProjectMember[];
  onChange: (id: string | null) => void;
}

/** Assignee picker (Figma "Field picker · PM · Assignee options"): label, "Unassigned", then the project members. */
export function AssigneeSelect({ value, current, members, onChange }: Props) {
  const options: { id: string | null; name: string }[] = [
    { id: null, name: 'Unassigned' },
    ...members.map((m) => ({ id: m.user_id, name: m.name })),
  ];
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, [open]);

  const openList = () => {
    setActive(Math.max(0, options.findIndex((o) => o.id === value)));
    setOpen(true);
  };
  const choose = (id: string | null) => {
    setOpen(false);
    if (id !== value) onChange(id);
    root.current?.querySelector('button')?.focus();
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    const n = options.length;
    if (e.key === 'Escape' && open) {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) return openList();
      setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : -1) + n) % n);
    } else if ((e.key === 'Enter' || e.key === ' ') && open) {
      e.preventDefault();
      choose(options[active].id);
    }
  };

  const label = current?.name ?? 'Unassigned';

  return (
    <div className="as" ref={root} onKeyDown={onKeyDown}>
      <button type="button" className={open ? 'ps-btn open' : 'ps-btn'} aria-haspopup="listbox" aria-expanded={open} aria-label="Assignee" onClick={() => (open ? setOpen(false) : openList())}>
        {label}
      </button>
      {open && (
        <div className="as-pop">
          <p className="as-title" id="as-title">Assignee</p>
          <ul role="listbox" aria-labelledby="as-title">
            {options.map((o, i) => (
              <li
                key={o.id ?? 'none'}
                role="option"
                aria-selected={o.id === value}
                className={i === active ? 'active' : undefined}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(o.id)}
              >
                {o.name}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
