'use strict';

// Sélecteur d'entreprise partagé (markup : dashboard/_company_combobox.html).
// Chargé par base.html, donc disponible sur toutes les pages.
//
//   CompanyCombobox.init({
//     root: document.getElementById('company-combobox'),
//     companies: [{id, name}, ...],
//     selected: {company_id, company_name} | null,   // valeur affichée au départ
//     onSelect: function (id, name) { ... },
//     persist: true,   // mémorise le choix pour les autres pages (défaut : true)
//   });
window.CompanyCombobox = (function () {
  // Emplacement localStorage partagé entre toutes les pages.
  var STORAGE_KEY = 'selected-company-id';

  // Identifiant mémorisé, s'il désigne une entreprise de la liste.
  function savedId(companies) {
    var id;
    try { id = parseInt(localStorage.getItem(STORAGE_KEY), 10); } catch (e) { return null; }
    if (!id) return null;
    return companies.some(function (c) { return c.id === id; }) ? id : null;
  }

  function remember(id) {
    try { localStorage.setItem(STORAGE_KEY, String(id)); } catch (e) { /* stockage indisponible */ }
  }

  function init(opts) {
    var root = opts.root;
    if (!root || root.dataset.bound) return null;
    var input = root.querySelector('.company-combobox__input');
    var listbox = root.querySelector('.company-combobox__listbox');
    if (!input || !listbox) return null;
    root.dataset.bound = '1';

    var companies = opts.companies || [];
    var persist = opts.persist !== false;
    var selected = null;
    var refocusing = false;

    function setSelected(id, name) {
      selected = id;
      input.value = name || '';
    }

    function options() {
      return Array.prototype.slice.call(listbox.querySelectorAll('[role="option"]'));
    }

    function render(filter) {
      var q = filter.toLowerCase();
      listbox.textContent = '';
      companies.forEach(function (c) {
        if (!c.name.toLowerCase().includes(q)) return;
        var li = document.createElement('li');
        li.className = 'company-combobox__option';
        li.setAttribute('role', 'option');
        li.setAttribute('tabindex', '-1');
        li.setAttribute('aria-selected', String(c.id === selected));
        li.dataset.id = c.id;
        li.textContent = c.name;
        listbox.appendChild(li);
      });
    }

    function open() {
      render(input.value);
      listbox.hidden = false;
      root.setAttribute('aria-expanded', 'true');
    }

    function close() {
      listbox.hidden = true;
      root.setAttribute('aria-expanded', 'false');
    }

    function choose(li) {
      var id = parseInt(li.dataset.id, 10);
      var name = li.textContent;
      setSelected(id, name);
      close();
      // Rend le focus au champ sans rouvrir la liste (focus est synchrone).
      refocusing = true;
      input.focus();
      refocusing = false;
      if (persist) remember(id);
      if (opts.onSelect) opts.onSelect(id, name);
    }

    // Tout le texte est sélectionné au focus : on tape directement un autre nom,
    // et la liste s'ouvre complète au lieu d'être filtrée sur le nom courant.
    function openFull() {
      render('');
      listbox.hidden = false;
      root.setAttribute('aria-expanded', 'true');
    }

    input.addEventListener('focus', function () {
      if (refocusing) return;
      input.select();
      openFull();
    });
    input.addEventListener('click', function () {
      if (listbox.hidden) openFull();
    });
    input.addEventListener('input', open);

    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') {
        if (listbox.hidden) open();
        var first = options()[0];
        if (first) { e.preventDefault(); first.focus(); }
      } else if (e.key === 'Enter') {
        var only = options();
        if (!listbox.hidden && only.length === 1) { e.preventDefault(); choose(only[0]); }
      } else if (e.key === 'Escape') {
        close();
      }
    });

    listbox.addEventListener('keydown', function (e) {
      var opts_ = options();
      var idx = opts_.indexOf(document.activeElement);
      if (e.key === 'ArrowDown' && idx < opts_.length - 1) {
        e.preventDefault(); opts_[idx + 1].focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (idx > 0) opts_[idx - 1].focus(); else input.focus();
      } else if (e.key === 'Enter' && idx >= 0) {
        e.preventDefault(); choose(opts_[idx]);
      } else if (e.key === 'Escape') {
        close(); input.focus();
      }
    });

    listbox.addEventListener('click', function (e) {
      var li = e.target.closest('[role="option"]');
      if (li) choose(li);
    });

    // Clic à l'extérieur : on ferme et on réaffiche l'entreprise en cours si
    // l'utilisateur avait commencé à taper sans choisir.
    document.addEventListener('click', function (e) {
      if (root.contains(e.target) || listbox.hidden) return;
      close();
      var current = companies.find(function (c) { return c.id === selected; });
      input.value = current ? current.name : '';
    });

    var initial = opts.selected;
    if (initial && initial.company_id != null) {
      setSelected(initial.company_id, initial.company_name);
    }

    return { setSelected: setSelected, close: close };
  }

  return { STORAGE_KEY: STORAGE_KEY, savedId: savedId, init: init };
})();
