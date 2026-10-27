import { useEffect, useRef, useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useAssignableUsers, type AssignableUser } from '@/features/tasks/tasksApi';

interface Props {
  selected: AssignableUser[];
  onChange: (next: AssignableUser[]) => void;
}

const AVATAR_COLORS = ['#295cba', '#0a7a6e', '#b06114', '#7a3fa0', '#a21d30'];

export const initialsOf = (name: string) =>
  name
    .split(' ')
    .filter(Boolean)
    .map((p) => p.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase();

const colorOf = (id: string) => AVATAR_COLORS[[...id].reduce((n, c) => n + c.charCodeAt(0), 0) % AVATAR_COLORS.length];

/** Figma "Field · Assign members": search-and-add combobox with removable teammate chips underneath (GET /users). */
export function MemberPicker({ selected, onChange }: Props) {
  const { t } = usePrefs();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const root = useRef<HTMLDivElement>(null);
  const users = useAssignableUsers(term, open);
  const chosen = new Set(selected.map((u) => u.id));
  const options = (users.data?.items ?? []).filter((u) => !chosen.has(u.id));

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

  const add = (u: AssignableUser) => {
    onChange([...selected, u]);
    setSearch('');
    setTerm('');
    setActive(0);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    const n = options.length;
    if (e.key === 'Escape') setOpen(false);
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      setOpen(true);
      if (n) setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : -1) + n) % n);
    } else if (e.key === 'Enter' && open) {
      e.preventDefault();
      if (n) add(options[active]);
    }
  };

  return (
    <>
      <div className="mp" ref={root} onKeyDown={onKeyDown}>
        <input
          id="members"
          className="input"
          role="combobox"
          aria-expanded={open}
          aria-controls="members-list"
          aria-autocomplete="list"
          autoComplete="off"
          placeholder={t('Search people and add members')}
          value={search}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setSearch(e.target.value);
            setOpen(true);
          }}
        />
        {open && (
          <ul className="mp-pop" id="members-list" role="listbox" aria-label={t('People')}>
            {options.length === 0 && <li className="mp-empty">{t(users.isPending ? 'Loading…' : 'No people found')}</li>}
            {options.map((u, i) => (
              <li
                key={u.id}
                role="option"
                aria-selected={false}
                className={i === active ? 'active' : undefined}
                onMouseEnter={() => setActive(i)}
                onClick={() => add(u)}
              >
                {u.name}
                <span className="muted small">{u.email}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {selected.length > 0 && (
        <ul className="chips" aria-label={t('Selected members')}>
          {selected.map((u) => (
            <li className="chip" key={u.id}>
              <span className="chip-av" style={{ background: colorOf(u.id) }} aria-hidden="true">
                {initialsOf(u.name)}
              </span>
              <span className="chip-name">{u.name}</span>
              <button type="button" aria-label={t('Remove {name}', { name: u.name })} onClick={() => onChange(selected.filter((s) => s.id !== u.id))}>
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
