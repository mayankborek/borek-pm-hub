/** Blocks user zoom: Ctrl/Cmd + wheel, Ctrl/Cmd + (+ / - / 0), and Safari pinch gestures. */
export function disableZoom() {
  const opts = { passive: false } as const;
  document.addEventListener('wheel', (e) => { if (e.ctrlKey || e.metaKey) e.preventDefault(); }, opts);
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && ['+', '=', '-', '_', '0'].includes(e.key)) e.preventDefault();
  });
  for (const type of ['gesturestart', 'gesturechange', 'gestureend']) {
    document.addEventListener(type, (e) => e.preventDefault(), opts);
  }
}
