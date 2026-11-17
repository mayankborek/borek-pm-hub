import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Avatar } from '@/features/tasks/TaskParts';
import { PRIORITY_OPTIONS, PriorityIndicator } from '@/features/tasks/PrioritySelect';
import { useProjectMembers, type Task, type TaskPriority } from '@/features/tasks/tasksApi';
import { usePrefs } from '@/shared/prefs/PrefsContext';

interface Option {
  key: string;
  node: ReactNode;
  selected: boolean;
  onPick: () => void;
}

/** Dropdown for a board card. The list is portalled and fixed-positioned so the column's scroll area cannot clip it. */
function CardMenu({ label, trigger, options, empty }: { label: string; trigger: ReactNode; options: Option[]; empty?: string }) {
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (!pos) return;
    const outside = (e: Event) => !list.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node);
    const away = (e: Event) => outside(e) && setPos(null);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setPos(null);
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    window.addEventListener('scroll', away, true);
    window.addEventListener('resize', away);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', esc);
      window.removeEventListener('scroll', away, true);
      window.removeEventListener('resize', away);
    };
  }, [pos]);

  // The card is a link: keep clicks on the picker from navigating to the task.
  const stop = (e: React.SyntheticEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };
  const pick = (o: Option) => {
    setPos(null);
    if (!o.selected) o.onPick();
  };

  return (
    <span className="kpick" onClick={stop}>
      <button
        ref={btn}
        type="button"
        className="kpick-btn"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={!!pos}
        onClick={(e) => {
          stop(e);
          if (pos) return setPos(null);
          const r = e.currentTarget.getBoundingClientRect();
          setPos({ top: r.bottom + 4, left: Math.max(8, Math.min(r.left, window.innerWidth - 228)) });
        }}
      >
        {trigger}
      </button>
      {pos &&
        createPortal(
          <ul ref={list} className="kpick-list" role="listbox" aria-label={label} style={{ top: pos.top, left: pos.left }}>
            {options.length === 0 && <li className="kpick-empty">{empty}</li>}
            {options.map((o) => (
              <li
                key={o.key}
                role="option"
                aria-selected={o.selected}
                tabIndex={0}
                onClick={() => pick(o)}
                onKeyDown={(e) => {
                  if (e.key !== 'Enter' && e.key !== ' ') return;
                  e.preventDefault();
                  pick(o);
                }}
              >
                {o.node}
              </li>
            ))}
          </ul>,
          document.body,
        )}
    </span>
  );
}

export function CardPriority({ task, editable, onChange }: { task: Task; editable: boolean; onChange: (p: TaskPriority) => void }) {
  const { t } = usePrefs();
  const current = PRIORITY_OPTIONS.find((o) => o.value === task.priority) ?? PRIORITY_OPTIONS[2];
  const icon = <img src={current.icon} alt={t(current.label)} title={t(current.label)} width={16} height={16} />;
  if (!editable) return icon;
  return (
    <CardMenu
      label={t('Priority')}
      trigger={icon}
      options={PRIORITY_OPTIONS.map((o) => ({
        key: o.value,
        node: <PriorityIndicator priority={o.value} />,
        selected: o.value === task.priority,
        onPick: () => onChange(o.value),
      }))}
    />
  );
}

export function CardAssignee({ task, editable, onChange }: { task: Task; editable: boolean; onChange: (id: string | null) => void }) {
  const { t } = usePrefs();
  const [wanted, setWanted] = useState(false);
  const members = useProjectMembers(wanted ? task.project_id : undefined);
  const face = task.assignee ? (
    <Avatar user={task.assignee} round />
  ) : (
    <span className="avatar round unassigned" title={t('Unassigned')} aria-label={t('Unassigned')}>
      ?
    </span>
  );
  if (!editable) return face;
  return (
    <span onMouseEnter={() => setWanted(true)} onFocus={() => setWanted(true)} onTouchStart={() => setWanted(true)}>
      <CardMenu
        label={t('Assignee')}
        trigger={face}
        empty={t(members.isPending ? 'Loading…' : 'No people found')}
        options={[
          { key: 'none', node: t('Unassigned'), selected: !task.assignee, onPick: () => onChange(null) },
          ...(members.data ?? []).map((m) => ({
            key: m.user_id,
            node: m.name,
            selected: m.user_id === task.assignee?.id,
            onPick: () => onChange(m.user_id),
          })),
        ]}
      />
    </span>
  );
}
