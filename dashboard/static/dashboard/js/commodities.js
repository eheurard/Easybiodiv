/* Fiche commodité : confirmation avant suppression d'un modificateur. */
(function () {
  'use strict';
  document.addEventListener('click', function (event) {
    var button = event.target.closest('button[data-confirm]');
    if (!button) { return; }
    if (!window.confirm(button.getAttribute('data-confirm'))) {
      event.preventDefault();
    }
  });
})();
