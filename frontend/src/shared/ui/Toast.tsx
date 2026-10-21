import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import './toast.css';

type Variant = 'success' | 'error' | 'info';
interface ToastItem {
  id: number;
  variant: Variant;
  message: string;
}

interface ToastApi {
  success: (message: string) => void;
  info: (message: string) => void;
  /** Errors stay until dismissed so the user can't miss a failure. */
  error: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);
const AUTO_DISMISS_MS = 4000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setItems((p) => p.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (variant: Variant, message: string) => {
      const id = nextId.current++;
      setItems((p) => [...p, { id, variant, message }]);
      if (variant !== 'error') setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({ success: (m) => push('success', m), info: (m) => push('info', m), error: (m) => push('error', m) }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="region" aria-label="Notifications">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.variant}`} role={t.variant === 'error' ? 'alert' : 'status'}>
            <span>{t.message}</span>
            <button type="button" aria-label="Dismiss notification" onClick={() => dismiss(t.id)}>
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
}
