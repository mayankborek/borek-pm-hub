import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '@/shared/api/client';

/** Best-effort message from an API error body ({detail: string}), else a generic fallback. */
export function errorText(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === 'string') return detail;
  }
  return fallback;
}

interface MenuProps {
  name: string;
  canMoveLeft: boolean;
  canMoveRight: boolean;
  canDelete: boolean;
  onRename: () => void;
  onMove: (dir: -1 | 1) => void;
  onDelete: () => void;
}

/** "⋯" trigger and Status actions menu (Figma "Board status actions menu · V1"). PM only. */
export function StatusMenu({ name, canMoveLeft, canMoveRight, canDelete, onRename, onMove, onDelete }: MenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  const run = (fn: () => void) => () => {
    setOpen(false);
    fn();
  };

  return (
    <div className="smenu" ref={ref}>
      <button type="button" className="smenu-trigger" aria-label={`Actions for ${name}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        ⋯
      </button>
      {open && (
        <div className="smenu-list" role="menu" aria-label="Status actions">
          <span className="smenu-title">Status actions</span>
          <button type="button" role="menuitem" onClick={run(onRename)}>
            Rename status
          </button>
          <button type="button" role="menuitem" disabled={!canMoveLeft} onClick={run(() => onMove(-1))}>
            Move left
          </button>
          <button type="button" role="menuitem" disabled={!canMoveRight} onClick={run(() => onMove(1))}>
            Move right
          </button>
          <hr />
          <button type="button" role="menuitem" className="danger" disabled={!canDelete} title={canDelete ? undefined : 'A project needs at least one status'} onClick={run(onDelete)}>
            Delete status
          </button>
        </div>
      )}
    </div>
  );
}

/** Inline rename of a column heading. Enter saves, Escape cancels. */
export function RenameInput({
  initial,
  taken,
  onSave,
  onCancel,
}: {
  initial: string;
  taken: (name: string) => boolean;
  onSave: (name: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  const name = value.trim();
  const clash = name.toLowerCase() !== initial.toLowerCase() && taken(name);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!name || clash) return;
    if (name === initial) onCancel();
    else onSave(name);
  };
  return (
    <form className="rename" onSubmit={submit}>
      <input
        autoFocus
        aria-label="Status name"
        aria-invalid={clash}
        maxLength={50}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        onBlur={onCancel}
      />
      {clash && <span className="rename-err">That status already exists.</span>}
    </form>
  );
}

type CreatorState = 'closed' | 'open' | 'saving' | 'success';

/** "+ Add status" button and inline creator (Figma "Board status creator · V1"). */
export function StatusCreator({
  taken,
  create,
}: {
  taken: (name: string) => boolean;
  create: (name: string) => Promise<unknown>;
}) {
  const [state, setState] = useState<CreatorState>('closed');
  const [name, setName] = useState('');
  const [added, setAdded] = useState('');
  const [error, setError] = useState('');
  const timer = useRef<number>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const close = () => {
    setState('closed');
    setName('');
    setError('');
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return setError('Enter a status name.');
    if (taken(trimmed)) return setError('That status already exists.');
    setError('');
    setState('saving');
    try {
      await create(trimmed);
      setAdded(trimmed);
      setName('');
      setState('success');
      timer.current = window.setTimeout(() => setState('closed'), 2500);
    } catch (err) {
      setError(errorText(err, 'Could not add the status. Try again.'));
      setState('open');
    }
  };

  if (state === 'closed')
    return (
      <button type="button" className="screator-btn" onClick={() => setState('open')}>
        <b>+</b> Add status
      </button>
    );
  if (state === 'success')
    return (
      <button type="button" className="screator success" onClick={close}>
        <strong>{added} added</strong>
        <span>Your new column is ready.</span>
      </button>
    );

  const saving = state === 'saving';
  return (
    <form className="screator" onSubmit={(e) => void submit(e)} onKeyDown={(e) => e.key === 'Escape' && !saving && close()}>
      <strong>{saving ? 'Adding status…' : error && taken(name.trim()) ? 'Add a status' : 'Add status'}</strong>
      <input
        autoFocus
        placeholder="e.g. QA review"
        aria-label="Status name"
        aria-invalid={!!error}
        maxLength={50}
        disabled={saving}
        value={name}
        onChange={(e) => {
          setName(e.target.value);
          setError('');
        }}
      />
      {error ? (
        <span className="screator-err" role="alert">
          {error}
        </span>
      ) : (
        <span className="screator-hint">{saving ? 'Please wait while it’s added.' : 'Give this step a clear name.'}</span>
      )}
      {!saving && (
        <div className="screator-actions">
          <button type="button" className="cancel" onClick={close}>
            Cancel
          </button>
          <button type="submit" className="primary">
            Add status
          </button>
        </div>
      )}
    </form>
  );
}
