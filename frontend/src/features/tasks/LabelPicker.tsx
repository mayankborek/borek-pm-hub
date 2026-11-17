import { useState, type KeyboardEvent } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useProjectLabels } from './tasksApi';

// Mirrors the backend limits (app/tasks/schemas.py).
const MAX_LABELS = 10;
const MAX_LENGTH = 30;

export function LabelChips({ labels }: { labels: string[] }) {
  if (!labels.length) return <span className="td-static">—</span>;
  return (
    <ul className="lb-chips">
      {labels.map((l) => (
        <li key={l} className="lb-chip">
          {l}
        </li>
      ))}
    </ul>
  );
}

/** Jira-style label field: each label is its own chip; type to search the project's labels or create a new one. */
export function LabelPicker({
  projectId,
  value,
  onChange,
  onSubmit,
}: {
  projectId: string;
  value: string[];
  onChange: (labels: string[]) => void;
  onSubmit: () => void;
}) {
  const { t } = usePrefs();
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const suggestions = useProjectLabels(projectId, text, open);

  const has = (name: string) => value.some((v) => v.toLowerCase() === name.toLowerCase());
  const full = value.length >= MAX_LABELS;
  const typed = text.trim().slice(0, MAX_LENGTH);
  const options = (suggestions.data ?? []).filter((s) => !has(s.name)).map((s) => s.name);
  const canCreate = !!typed && !has(typed) && !options.some((o) => o.toLowerCase() === typed.toLowerCase());
  const rows = [...options, ...(canCreate ? [typed] : [])];

  const add = (name: string) => {
    const label = name.trim().slice(0, MAX_LENGTH);
    if (!label || has(label) || full) return;
    onChange([...value, label]);
    setText('');
    setActive(0);
  };
  const remove = (name: string) => onChange(value.filter((v) => v !== name));

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      setOpen(true);
      if (rows.length) setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : rows.length - 1)) % rows.length);
    } else if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      if (text.trim()) add(open && rows[active] ? rows[active] : text);
      else if (e.key === 'Enter') onSubmit();
    } else if (e.key === 'Backspace' && !text && value.length) {
      remove(value[value.length - 1]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="lb-picker">
      <div className="lb-box" onClick={(e) => (e.currentTarget.querySelector('input') as HTMLInputElement | null)?.focus()}>
        {value.map((l) => (
          <span key={l} className="lb-chip">
            {l}
            <button type="button" className="lb-x" aria-label={t('Remove {name}', { name: l })} onClick={() => remove(l)}>
              ×
            </button>
          </span>
        ))}
        <input
          role="combobox"
          aria-expanded={open}
          aria-label={t('Labels')}
          placeholder={full ? '' : t(value.length ? 'Add label' : 'Search or add labels')}
          value={text}
          maxLength={MAX_LENGTH}
          disabled={full}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onChange={(e) => {
            setText(e.target.value.replace(/,/g, ''));
            setActive(0);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && !full && rows.length > 0 && (
        <ul className="lb-menu" role="listbox">
          {rows.map((name, i) => (
            <li
              key={name}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'lb-opt on' : 'lb-opt'}
              // mousedown, not click: the input's blur would close the menu first.
              onMouseDown={(e) => {
                e.preventDefault();
                add(name);
              }}
            >
              {canCreate && i === rows.length - 1 ? `${t('Create')} “${name}”` : name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
