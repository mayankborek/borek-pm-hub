import { useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useProjectMembers } from './tasksApi';

/** The backend accepts at most 20 mentions per comment. */
export const MAX_MENTIONS = 20;

interface Props {
  projectId: string;
  value: string;
  onChange: (v: string) => void;
  label: string;
  placeholder?: string;
  autoFocus?: boolean;
}

/** `@Name` tokens in `body` that match a project member, as the ids the backend wants in `mention_ids`. */
export const mentionIdsFor = (body: string, members: { user_id: string; name: string }[]) =>
  members.filter((m) => m.name && body.includes(`@${m.name}`)).map((m) => m.user_id).slice(0, MAX_MENTIONS);

/** Text input that suggests project members after an `@`; picking one inserts `@Name`. */
export function MentionInput({ projectId, value, onChange, label, placeholder, autoFocus }: Props) {
  const { t } = usePrefs();
  const members = useProjectMembers(projectId).data ?? [];
  const [open, setOpen] = useState(true);
  const match = /(?:^|\s)@([^@\s]*)$/.exec(value);
  const query = match?.[1].toLowerCase() ?? '';
  const options = match && open ? members.filter((m) => m.name.toLowerCase().includes(query)).slice(0, 6) : [];

  const pick = (name: string) => {
    onChange(value.replace(/@[^@\s]*$/, `@${name} `));
    setOpen(true);
  };

  return (
    <span className="td-mention">
      <input
        aria-label={label}
        placeholder={placeholder}
        maxLength={5000}
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onKeyDown={(e) => e.key === 'Escape' && options.length > 0 && (e.stopPropagation(), setOpen(false))}
      />
      {options.length > 0 && (
        <ul className="td-mention-list" role="listbox" aria-label={t('Mention a project member')}>
          {options.map((m) => (
            <li key={m.user_id} role="option" aria-selected={false}>
              <button type="button" className="td-link" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(m.name)}>
                {m.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}
