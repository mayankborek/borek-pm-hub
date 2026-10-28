import type { ReactNode } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';

interface Props {
  title: string;
  description?: string;
  children?: ReactNode;
}

/** Temporary page body. Replace with the real feature UI as tickets land. */
export function PagePlaceholder({ title, description, children }: Props) {
  const { t } = usePrefs();
  return (
    <section className="page-body">
      <h1 className="page-title">{t(title)}</h1>
      {description && <p className="page-desc">{t(description)}</p>}
      <div className="placeholder">{t('Coming soon')}</div>
      {children}
    </section>
  );
}
