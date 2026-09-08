// ── Disposition des pages carte ─────────────────────────────────────────────
// Pilote les overlays de la scène plein écran (.map-stage) : repli du panneau
// latéral droit et ouverture du tiroir bas. Chargé uniquement par les
// templates à carte ; LEAP Locate garde son propre pilotage dans
// leap_locate.js et n'utilise donc pas ce fichier.
(function () {
  document.addEventListener('DOMContentLoaded', function () {

    // ── Panneau latéral droit ────────────────────────────────────────────
    document.querySelectorAll('.map-stage').forEach(function (stage) {
      const toggle = stage.querySelector('.map-panel__toggle');
      const reopen = stage.querySelector('.map-panel__reopen');
      if (!toggle || !reopen) return;

      function setCollapsed(collapsed) {
        stage.classList.toggle('is-panel-collapsed', collapsed);
        toggle.setAttribute('aria-expanded', String(!collapsed));
        reopen.setAttribute('aria-expanded', String(!collapsed));
      }

      toggle.addEventListener('click', function () { setCollapsed(true); });
      reopen.addEventListener('click', function () { setCollapsed(false); });
    });

    // ── Tiroir bas ───────────────────────────────────────────────────────
    document.querySelectorAll('.map-drawer').forEach(function (drawer) {
      const handle = drawer.querySelector('.map-drawer__handle');
      if (!handle) return;

      handle.addEventListener('click', function () {
        const open = drawer.classList.toggle('is-open');
        handle.setAttribute('aria-expanded', String(open));
      });
    });

  });
})();
