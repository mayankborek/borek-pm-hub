import { Link } from 'react-router-dom';
import { usePrefs } from '@/shared/prefs/PrefsContext';

export function Back({ to, label }: { to: string; label: string }) {
  const { t } = usePrefs();
  return (
    <Link className="ad-back" to={to}>
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.1" aria-hidden="true"><path d="M13 8H3m4.5-4.5L3 8l4.5 4.5" /></svg>
      {t(label)}
    </Link>
  );
}
