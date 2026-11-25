const base = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true } as const;

/** Line icons used by the PM dashboard and project cards (Figma "Dashboard" and "Projects"). */
export function PmIcon({ name }: { name: 'folder' | 'layers' | 'ban' | 'clock' | 'briefcase' | 'warning' | 'chevron' }) {
  switch (name) {
    case 'folder':
      return <svg {...base}><path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.2l2 2.5h8.8A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z" /></svg>;
    case 'layers':
      return <svg {...base}><path d="m12 3 9 4.5-9 4.5-9-4.5z" /><path d="m3 12 9 4.5 9-4.5" /><path d="m3 16.5 9 4.5 9-4.5" /></svg>;
    case 'ban':
      return <svg {...base}><circle cx="12" cy="12" r="9" /><path d="m5.6 5.6 12.8 12.8" /></svg>;
    case 'clock':
      return <svg {...base}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>;
    case 'briefcase':
      return <svg {...base}><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7" /><path d="M3 13h18" /></svg>;
    case 'warning':
      return <svg {...base}><path d="M12 4 2.8 19.5h18.4z" /><path d="M12 10v4.5M12 17.2v.1" /></svg>;
    case 'chevron':
      return <svg {...base} width={18} height={18}><path d="m6 9 6 6 6-6" /></svg>;
  }
}
