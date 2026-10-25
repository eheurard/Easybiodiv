/* Fiche commodité : édition en place, modales des modificateurs, aperçu du facteur ajusté
   et confirmation avant suppression. JS natif, chargé en defer. */
(function () {
  'use strict';

  var LOCALE = typeof APP_LOCALE !== 'undefined' ? APP_LOCALE
    : (document.documentElement.lang === 'en' ? 'en-GB' : 'fr-FR');

  // ── Confirmation avant suppression ──────────────────────────────────────
  document.addEventListener('click', function (event) {
    var button = event.target.closest('button[data-confirm]');
    if (button && !window.confirm(button.getAttribute('data-confirm'))) {
      event.preventDefault();
    }
  });

  // ── Édition en place (identité, dépendances, sources) ──────────────────
  function editScope(button) {
    var target = button.getAttribute('data-edit-target');
    return target ? document.getElementById(target) : button.closest('[data-edit-scope]');
  }

  function setEditing(scope, editing) {
    if (!scope) { return; }
    scope.setAttribute('data-editing', editing ? 'true' : 'false');
    if (editing) {
      var first = scope.querySelector('[data-edit-only] input, [data-edit-only] select, '
        + '[data-edit-only] textarea');
      if (first) { first.focus(); }
    }
  }

  document.addEventListener('click', function (event) {
    var toggle = event.target.closest('[data-edit-toggle]');
    if (toggle) {
      setEditing(editScope(toggle), true);
      return;
    }
    var cancel = event.target.closest('[data-edit-cancel]');
    if (cancel) {
      var scope = cancel.closest('[data-edit-scope]');
      if (scope && scope.tagName === 'FORM') { scope.reset(); }
      setEditing(scope, false);
    }
  });

  // ── Modales ─────────────────────────────────────────────────────────────
  document.addEventListener('click', function (event) {
    var opener = event.target.closest('[data-dialog-open]');
    if (opener) {
      var dialog = document.getElementById(opener.getAttribute('data-dialog-open'));
      if (dialog && typeof dialog.showModal === 'function') {
        dialog.showModal();
        refreshPreviews(dialog);
      }
      return;
    }
    var closer = event.target.closest('[data-dialog-close]');
    if (closer) {
      var parent = closer.closest('dialog');
      if (parent) { parent.close(); }
    }
  });

  // ── Aperçu du facteur ajusté ────────────────────────────────────────────
  var resolved = {};
  var resolvedNode = document.getElementById('commodity-resolved-factors');
  if (resolvedNode) {
    try { resolved = JSON.parse(resolvedNode.textContent) || {}; } catch (e) { resolved = {}; }
  }

  function parseNumber(text) {
    var cleaned = String(text || '').replace(/\s/g, '').replace(',', '.');
    if (cleaned === '' || !/^[-+]?\d*\.?\d+(e[-+]?\d+)?$/i.test(cleaned)) { return null; }
    return parseFloat(cleaned);
  }

  function formatNumber(value) {
    return value.toLocaleString(LOCALE, { maximumSignificantDigits: 6 });
  }

  function refreshPreview(row) {
    var cell = row.querySelector('[data-effect-preview]');
    var select = row.querySelector('select');
    var input = row.querySelector('input[name$="-percent"]');
    if (!cell || !select || !input) { return; }
    var base = resolved[select.value];
    var percent = parseNumber(input.value);
    cell.textContent = '';
    if (base === undefined || base === null || percent === null) {
      cell.textContent = '—';
      return;
    }
    var adjusted = base * Math.max(0, 1 + percent / 100);
    cell.appendChild(document.createTextNode(formatNumber(base) + ' → '));
    var strong = document.createElement('b');
    strong.textContent = formatNumber(adjusted);
    cell.appendChild(strong);
  }

  function refreshPreviews(root) {
    root.querySelectorAll('[data-effect-row]').forEach(refreshPreview);
  }

  document.addEventListener('input', function (event) {
    var row = event.target.closest('[data-effect-row]');
    if (row) { refreshPreview(row); }
  });

  document.addEventListener('change', function (event) {
    var row = event.target.closest('[data-effect-row]');
    if (!row) { return; }
    if (event.target.matches('input[type="checkbox"][name$="-DELETE"]')) {
      row.classList.toggle('is-removed', event.target.checked);
    }
    refreshPreview(row);
  });

  // ── Lignes d'effet : ajout et effacement ────────────────────────────────
  document.addEventListener('click', function (event) {
    var add = event.target.closest('[data-effects-add]');
    if (add) {
      var form = add.closest('form');
      var prefix = form.getAttribute('data-effects-prefix');
      var total = form.querySelector('input[name="' + prefix + '-TOTAL_FORMS"]');
      var template = form.querySelector('template[data-effects-template]');
      var rows = form.querySelector('[data-effects-rows]');
      if (!total || !template || !rows) { return; }
      var index = parseInt(total.value, 10) || 0;
      var html = template.innerHTML.replace(/__prefix__/g, String(index));
      rows.insertAdjacentHTML('beforeend', html.trim());
      total.value = String(index + 1);
      var added = rows.lastElementChild;
      refreshPreview(added);
      var select = added.querySelector('select');
      if (select) { select.focus(); }
      return;
    }
    var clear = event.target.closest('[data-effect-clear]');
    if (clear) {
      // Une ligne nouvelle laissée vide est ignorée par le formset.
      var row = clear.closest('[data-effect-row]');
      row.querySelectorAll('select, input[type="text"]').forEach(function (field) {
        field.value = '';
      });
      refreshPreview(row);
    }
  });

  // ── Sélecteur « + pays ou région » : envoi au choix ─────────────────────
  document.querySelectorAll('form[data-autosubmit]').forEach(function (form) {
    var button = form.querySelector('[data-autosubmit-button]');
    if (button) { button.hidden = true; }
    var select = form.querySelector('select');
    if (select) {
      select.addEventListener('change', function () {
        if (select.value) { form.submit(); }
      });
    }
  });

  // ── Réouverture après une erreur de saisie ──────────────────────────────
  document.querySelectorAll('dialog[data-open-on-load]').forEach(function (dialog) {
    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
      refreshPreviews(dialog);
    }
  });
})();
