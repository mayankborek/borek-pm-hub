import { useEffect, useRef, useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
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
  const { t } = usePrefs();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const [picked, setPicked] = useState<{ id: string | null; name: string } | null>(null);
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
    setPicked(id ? (options.find((o) => o.id === id) ?? null) : null);
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

  // `value` may be a staged choice that differs from the saved assignee in `current`.
  const label =
    value === null ? 'Unassigned' : value === current?.id ? current.name : picked?.id === value ? picked.name : 'Unassigned';

  return (
    <div className="as" ref={root} onKeyDown={onKeyDown}>
      <button type="button" className={open ? 'ps-btn open' : 'ps-btn'} aria-haspopup="listbox" aria-expanded={open} aria-label={t('Assignee')} onClick={() => (open ? setOpen(false) : openList())}>
        {t(label)}
      </button>
      {open && (
        <div className="as-pop">
          <p className="as-title" id="as-title">{t('Assignee')}</p>
          <input
            className="as-search"
            type="search"
            autoFocus
            placeholder={t('Search people')}
            aria-label={t('Search people')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <ul role="listbox" aria-labelledby="as-title">
            {options.length === 0 && <li className="as-empty">{t(users.isPending ? 'Loading…' : 'No people found')}</li>}
            {options.map((o, i) => (
              <li
                key={o.id ?? 'none'}
                role="option"
                aria-selected={o.id === value}
                className={i === active ? 'active' : undefined}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(o.id)}
              >
                {t(o.name)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
