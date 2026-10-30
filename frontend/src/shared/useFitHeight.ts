import { useLayoutEffect, type RefObject } from 'react';

const MIN_SCALE = 0.5;

/**
 * Keeps `inner` fully visible inside `host` without a vertical scrollbar: when the content is taller than the
 * host, it is scaled down uniformly (width compensated) so every component keeps its proportions.
 */
export function useFitHeight(host: RefObject<HTMLElement | null>, inner: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    const h = host.current;
    const i = inner.current;
    if (!h || !i) return;
    let raf = 0;
    let last = 1;

    const fit = () => {
      const cs = getComputedStyle(h);
      const avail = h.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
      if (avail <= 0) return;
      i.style.transform = '';
      i.style.width = '';
      i.style.minHeight = `${avail}px`;
      const natural = i.offsetHeight;
      const s = Math.max(MIN_SCALE, Math.min(1, avail / natural));
      if (s < 1) {
        i.style.transformOrigin = 'top left';
        i.style.transform = `scale(${s})`;
        i.style.width = `${100 / s}%`;
        i.style.minHeight = `${avail / s}px`;
      }
      last = s;
    };
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(fit);
    };

    fit();
    const ro = new ResizeObserver(() => {
      // Ignore the size change we caused ourselves by scaling.
      if (last < 1 && Math.abs(i.offsetWidth * last - h.clientWidth) < 2 && Math.abs(i.offsetHeight * last - h.clientHeight) < 4) return;
      schedule();
    });
    ro.observe(h);
    const mo = new MutationObserver(schedule);
    mo.observe(i, { childList: true, subtree: true, characterData: true });
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      mo.disconnect();
    };
  }, [host, inner]);
}
