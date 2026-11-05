/* Shared behaviour: dialogs and the notifications popover. */
(function () {
  document.addEventListener('click', function (e) {
    var open = e.target.closest('[data-open-dialog]');
    if (open) {
      e.preventDefault();
      var d = document.getElementById(open.getAttribute('data-open-dialog'));
      if (d) d.showModal();
      return;
    }
    var close = e.target.closest('[data-close-dialog]');
    if (close) {
      var host = close.closest('dialog');
      if (host) host.close();
      return;
    }
    // Click on the backdrop (the dialog element itself, not its content)
    if (e.target.matches && e.target.matches('dialog.dialog')) { e.target.close(); return; }

    // Notifications popover
    var toggle = e.target.closest('[data-notif-toggle]');
    var panel = document.getElementById('notifications');
    var btn = document.querySelector('[data-notif-toggle]');
    if (!panel || !btn) return;
    if (toggle) {
      var show = panel.hidden;
      panel.hidden = !show;
      btn.setAttribute('aria-expanded', String(show));
    } else if (!panel.hidden && !e.target.closest('#notifications')) {
      panel.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var panel = document.getElementById('notifications');
    var btn = document.querySelector('[data-notif-toggle]');
    if (panel && !panel.hidden) { panel.hidden = true; btn.setAttribute('aria-expanded', 'false'); btn.focus(); }
  });
})();
