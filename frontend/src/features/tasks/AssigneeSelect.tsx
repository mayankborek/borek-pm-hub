import { useEffect, useRef, useState } from 'react';
import { useAssignableUsers } from './tasksApi';

interface Props {
  value: string | null;
  /** Current assignee, shown even while the list is still loading. */
  current: { id: string; name: string } | null;
  onChange: (id: string | null) => void;
}

/**
 * Assignee picker (Figma "Field picker · PM · Assignee options"): label, search, "Unassigned", then every
 * developer (GET /users). Assigning someone who is not in the project yet adds them as a member.
 */
export function AssigneeSelect({ value, current, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const root = useRef<HTMLDivElement>(null);
  const users = useAssignableUsers(term, open);
  const options: { id: string | null; name: string }[] = [
    ...(term ? [] : [{ id: null, name: 'Unassigned' }]),
    ...(users.data?.items ?? []).map((u) => ({ id: u.id, name: u.name })),
  ];

  useEffect(() => {
    const id = setTimeout(() => setTerm(search), 250);
    return () => clearTimeout(id);
  }, [search]);
  useEffect(() => setActive(0), [term]);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, [open]);

  const openList = () => {
    setSearch('');
    setTerm('');
    setActive(0);
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
    } else if ((e.key === 'Enter' || (e.key === ' ' && (e.target as HTMLElement).tagName !== 'INPUT')) && open && n > 0) {
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
          <input
            className="as-search"
            type="search"
            autoFocus
            placeholder="Search people"
            aria-label="Search people"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <ul role="listbox" aria-labelledby="as-title">
            {options.length === 0 && <li className="as-empty">{users.isPending ? 'Loading…' : 'No people found'}</li>}
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
