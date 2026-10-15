import type { ReactNode } from 'react';

interface Props {
  title: string;
  description?: string;
  children?: ReactNode;
}

/** Temporary page body. Replace with the real feature UI as tickets land. */
export function PagePlaceholder({ title, description, children }: Props) {
  return (
    <section className="page-body">
      <h1 className="page-title">{title}</h1>
      {description && <p className="page-desc">{description}</p>}
      <div className="placeholder">Coming soon</div>
      {children}
    </section>
  );
}
