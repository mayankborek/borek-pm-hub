import type { CSSProperties, ReactNode } from 'react';

export function Bar({ value, style }: { value: number; style?: CSSProperties }) {
  return (
    <div className="cp-bar" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} style={style}>
      <i style={{ width: `${value}%` }} />
    </div>
  );
}

export function Badge({ tone, children }: { tone?: 'late' | 'plan'; children: ReactNode }) {
  return <span className={tone ? `cp-badge cp-${tone}` : 'cp-badge'}>{children}</span>;
}

export function Kpi({ label, value, hint, overview }: { label: string; value: ReactNode; hint: string; overview?: boolean }) {
  return (
    <div className={overview ? 'cp-card cp-kpi cp-o' : 'cp-card cp-kpi'}>
      <div className="cp-l">{label}</div>
      <div className="cp-v">{value}</div>
      <div className="cp-d">{hint}</div>
    </div>
  );
}
