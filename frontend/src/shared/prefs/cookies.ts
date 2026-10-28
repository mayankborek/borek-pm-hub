const ONE_YEAR = 60 * 60 * 24 * 365;

export function readCookie(name: string): string | null {
  try {
    const match = document.cookie.split('; ').find((c) => c.startsWith(`${name}=`));
    return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
  } catch {
    return null;
  }
}

export function writeCookie(name: string, value: string) {
  try {
    document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${ONE_YEAR}; SameSite=Lax`;
  } catch {
    /* cookies unavailable */
  }
}
