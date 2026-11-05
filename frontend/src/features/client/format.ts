const parse = (iso: string) => new Date(`${iso}T00:00:00Z`);
const fmt = (lang: string, iso: string, o: Intl.DateTimeFormatOptions) =>
  parse(iso).toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', { timeZone: 'UTC', ...o });

/** 06 Nov */
export const dayMonth = (lang: string, iso: string) => fmt(lang, iso, { day: '2-digit', month: 'short' }).replace('.', '');
/** 6 Nov 2026 */
export const longDate = (lang: string, iso: string) => fmt(lang, iso, { day: 'numeric', month: 'short', year: 'numeric' });
/** 2 Nov */
export const shortDate = (lang: string, iso: string) => fmt(lang, iso, { day: 'numeric', month: 'short' });
/** 02 Nov 2026 */
export const paddedDate = (lang: string, iso: string) => fmt(lang, iso, { day: '2-digit', month: 'short', year: 'numeric' });

/** 24–30 Oct 2026 (or 28 Oct – 3 Nov 2026 across months). */
export function dateRange(lang: string, start: string, end: string) {
  const s = parse(start);
  const e = parse(end);
  if (s.getUTCMonth() === e.getUTCMonth() && s.getUTCFullYear() === e.getUTCFullYear()) {
    const day = s.getUTCDate();
    return `${day}–${longDate(lang, end)}`;
  }
  return `${shortDate(lang, start)} – ${longDate(lang, end)}`;
}

export const initialsOf = (name: string) =>
  name
    .split(' ')
    .map((p) => p.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase();
