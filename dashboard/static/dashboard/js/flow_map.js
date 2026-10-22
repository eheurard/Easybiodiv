'use strict';

// Page « Carte des flux » : chargement des données, état de la page (groupes
// dépliés, blocs masqués, blocs déplacés, cadrage) et interactions de lecture.
// Le dessin est fait par FlowMapDraw (flow_map_draw.js).
//
// Point d'accroche pour la saisie (Task 8) :
//   FlowMap.state        état passé à FlowMapDraw.render (à modifier puis redraw())
//   FlowMap.model()      données affichées (réponse de l'API flow_map_data)
//   FlowMap.rules        FLOW_RULES sérialisé ({kind: {origins, destinations}})
//   FlowMap.kinds        [{value, label}]
//   FlowMap.canEdit      vrai pour un Créateur
//   FlowMap.svg          l'élément <svg> de la carte
//   FlowMap.redraw()     redessine sans recharger ; renvoie le résultat de render
//   FlowMap.reload()     recharge l'entreprise et l'année affichées, sans recadrer
//   FlowMap.load(id, y)  charge une entreprise / une année (y null : par défaut)
//   FlowMap.menuActions  entrées du menu « ⋯ » d'un bloc :
//                        {id, label: string, visible(node): bool, run(node)}
//   FlowMap.onRender     fonctions appelées après chaque dessin, avec le résultat
//   FlowMap.onTap        fonctions appelées pour un clic sans glisser (ou Entrée) :
//                        fn({type, key, port, keyboard}) -> true si traité (le
//                        comportement par défaut, déplier / replier, est alors sauté).
//                        type : 'block', 'frame', 'edge', 'port', 'band', 'background'
//   FlowMap.lastRender() dernier résultat de FlowMapDraw.render (ou null)
// Événements sur document : « flowmap:loaded » (detail : données) après chaque
// chargement ; « flowmap:changed », émis après une écriture, recharge la carte.
window.FlowMap = (function () {
  var MIN_SCALE = 0.2;        // unités SVG par pixel écran (zoom avant maximal)
  var MAX_SCALE = 6;          // zoom arrière maximal
  var MAX_FIT_SCALE = 1.5;    // cadrage initial : au-delà, texte illisible, on déplace la vue
  var DRAG_THRESHOLD = 4;

  var api = {
    state: { expanded: new Set(), hidden: new Set(), positions: new Map(), selectedEdge: null },
    rules: {},
    kinds: [],
    canEdit: false,
    svg: null,
    menuActions: [],
    onRender: [],
    onTap: [],
    model: function () { return current; },
    lastRender: function () { return last; },
    redraw: redraw,
    reload: function () { return reload(); },
    load: load,
  };

  var current = null;
  var target = null;          // dernière demande {companyId, year} (affichée ou en cours)
  var request = 0;            // numéro de la dernière demande : seule elle est affichée
  var pending = null;         // AbortController de la demande en cours
  var last = null;            // dernier résultat de FlowMapDraw.render
  var view = null;            // viewBox {x, y, width, height}
  var viewPx = null;          // taille en pixels pour laquelle `view` a été calculée
  var frame = 0;
  var els = {};

  function readJson(id) {
    var node = document.getElementById(id);
    return node ? JSON.parse(node.textContent) : null;
  }

  function resetState() {
    api.state.expanded.clear();
    api.state.hidden.clear();
    api.state.positions.clear();
    api.state.selectedEdge = null;
    api.state.trace = null;
  }

  // ── Chargement ───────────────────────────────────────────────────────────
  // Une demande plus récente annule la précédente : une réponse lente ne peut
  // pas remplacer la carte demandée ensuite. `keepView` garde le cadrage (après
  // une écriture) ; sinon la carte est recadrée.
  function load(companyId, year, keepView) {
    var url = FLOW_MAP_API_URL.replace('/0/', '/' + companyId + '/');
    if (year !== null && year !== undefined) url += '?year=' + encodeURIComponent(year);
    if (pending) pending.abort();
    var controller = new AbortController();
    var mine = ++request;
    pending = controller;
    target = { companyId: companyId, year: year };
    els.board.classList.add('is-loading');
    return fetch(url, { headers: { Accept: 'application/json' }, signal: controller.signal })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (mine !== request) return null;
        if (!current || current.company.id !== data.company.id) resetState();
        show(data, keepView);
        return data;
      })
      .catch(function (err) {
        if (mine !== request) return null;
        console.error('flow_map fetch failed:', err);
        clearMap();
        showMessage(gettext('Impossible de charger la carte des flux.'));
        return null;
      })
      .finally(function () {
        if (mine !== request) return;
        pending = null;
        els.board.classList.remove('is-loading');
      });
  }

  function reload() {
    if (!target) return null;
    return load(target.companyId, current ? current.year : target.year, true);
  }

  function show(data, keepView) {
    current = data;
    target = { companyId: data.company.id, year: data.year };
    api.canEdit = !!data.can_edit;
    api.state.editable = api.canEdit;
    closeMenu();
    renderYears(data);
    redraw();
    if (!keepView || !view) fitView();
    else applyView();
    document.dispatchEvent(new CustomEvent('flowmap:loaded', { detail: data }));
  }

  // Échec du chargement : rien de l'entreprise précédente ne doit rester affiché.
  function clearMap() {
    current = null;
    last = null;
    resetState();
    while (els.svg.firstChild) els.svg.removeChild(els.svg.firstChild);
    els.chip.hidden = true;
    closeMenu();
  }

  function showMessage(message) {
    els.empty.textContent = message;
    els.empty.hidden = false;
  }

  // ── Dessin ───────────────────────────────────────────────────────────────
  function redraw() {
    if (!current) return null;
    last = FlowMapDraw.render(els.svg, current, api.state);
    stretchBand();
    renderHiddenChip();
    renderEmpty();
    api.onRender.forEach(function (fn) { fn(last); });
    return last;
  }

  function scheduleRedraw() {
    if (frame) return;
    frame = requestAnimationFrame(function () { frame = 0; redraw(); });
  }

  function renderEmpty() {
    var empty = !last.edges.length && last.nodes.length <= 1;
    if (!empty) { els.empty.hidden = true; return; }
    var message = api.canEdit
      ? gettext('Aucun flux pour %(year)s. Ajoutez un bloc pour commencer la carte.')
      : gettext('Aucun flux enregistré pour %(year)s.');
    showMessage(interpolate(message, { year: current.year }, true));
  }

  function hiddenCount() {
    var known = new Set(current.blocks.map(function (b) { return b.key; }));
    current.groups.forEach(function (g) { known.add(g.key); });
    var n = 0;
    api.state.hidden.forEach(function (key) { if (known.has(key)) n += 1; });
    return n;
  }

  function renderHiddenChip() {
    var n = hiddenCount();
    els.chip.hidden = n === 0;
    els.chip.textContent = interpolate(
      ngettext('%(n)s bloc masqué', '%(n)s blocs masqués', n), { n: n }, true);
  }

  function renderYears(data) {
    els.year.textContent = '';
    data.years.slice().sort(function (a, b) { return b - a; }).forEach(function (year) {
      var option = document.createElement('option');
      option.value = String(year);
      option.textContent = String(year);
      els.year.appendChild(option);
    });
    els.year.value = String(data.year);
    els.yearOther.value = '';
  }

  // ── Vue : cadrage, zoom, déplacement ─────────────────────────────────────
  function applyView() {
    viewPx = size();
    els.svg.setAttribute('viewBox', [view.x, view.y, view.width, view.height].join(' '));
    stretchBand();
  }

  // Le bandeau du milieu couvre toute la largeur visible, son titre reste à l'écran.
  function stretchBand() {
    var rect = els.svg.querySelector('.fm-band__rect');
    var label = els.svg.querySelector('.fm-band__label');
    if (!rect || !view || !last) return;
    var left = Math.min(view.x, last.bounds.x);
    var right = Math.max(view.x + view.width, last.bounds.x + last.bounds.width);
    rect.setAttribute('x', left);
    rect.setAttribute('width', right - left);
    label.setAttribute('x', view.x + 16);
  }

  function size() {
    return { width: els.svg.clientWidth || 1, height: els.svg.clientHeight || 1 };
  }

  // Toute la carte dans le cadre, sans agrandir au-delà de l'échelle 1 ni
  // réduire au point de rendre le texte illisible (le haut reste alors visible).
  function fitView() {
    if (!last) return;
    var b = last.bounds;
    var s = size();
    var scale = Math.min(Math.max(b.width / s.width, b.height / s.height, 1), MAX_FIT_SCALE);
    view = { width: s.width * scale, height: s.height * scale };
    view.x = view.width > b.width ? b.x - (view.width - b.width) / 2 : b.x;
    view.y = b.y;
    applyView();
  }

  // Unités SVG par pixel. Mesurée sur la taille d'origine de la vue : après un
  // redimensionnement (panneau ouvert), onResize garde cette échelle.
  function scale() {
    return view.width / (viewPx || size()).width;
  }

  function toSvg(event) {
    var rect = els.svg.getBoundingClientRect();
    return {
      x: view.x + (event.clientX - rect.left) * scale(),
      y: view.y + (event.clientY - rect.top) * scale(),
    };
  }

  function onWheel(event) {
    if (!view) return;
    event.preventDefault();
    var factor = Math.exp(event.deltaY * 0.0015);
    var next = Math.min(Math.max(scale() * factor, MIN_SCALE), MAX_SCALE);
    factor = next / scale();
    var p = toSvg(event);
    view.x = p.x - (p.x - view.x) * factor;
    view.y = p.y - (p.y - view.y) * factor;
    view.width *= factor;
    view.height *= factor;
    applyView();
  }

  function onResize() {
    if (!view) return;
    var k = scale();
    var s = size();
    view.width = s.width * k;
    view.height = s.height * k;
    applyView();
  }

  // ── Glisser : fond (déplacer la vue) ou bloc (le déplacer) ────────────────
  var drag = null;

  function nodeOf(key) {
    return last && last.nodes.find(function (n) { return n.key === key; });
  }

  function onPointerDown(event) {
    if (event.button !== 0 || !view) return;
    closeMenu();
    if (event.target.closest('.fm-block__menu')) return;
    var port = event.target.closest('.fm-port');
    var block = event.target.closest('.fm-block');
    var frameEl = event.target.closest('.fm-frame');
    var edge = event.target.closest('.fm-edge');
    var start = { x: event.clientX, y: event.clientY };
    if (port) {
      drag = { type: 'port', key: block.dataset.key, port: port.dataset.port, start: start };
    } else if (block) {
      var node = nodeOf(block.dataset.key);
      drag = {
        type: 'block', key: block.dataset.key, start: start, origin: { x: node.x, y: node.y },
      };
    } else if (frameEl) {
      drag = { type: 'frame', key: frameEl.dataset.key, start: start };
    } else if (edge) {
      drag = { type: 'edge', key: edge.dataset.key, start: start };
    } else {
      drag = {
        type: 'view', start: start, origin: { x: view.x, y: view.y },
        band: !!event.target.closest('.fm-band'),
      };
    }
    drag.moved = false;
    els.svg.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event) {
    if (!drag) return;
    var dx = event.clientX - drag.start.x;
    var dy = event.clientY - drag.start.y;
    if (!drag.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    drag.moved = true;
    var k = scale();
    if (drag.type === 'view') {
      els.svg.classList.add('is-panning');
      view.x = drag.origin.x - dx * k;
      view.y = drag.origin.y - dy * k;
      applyView();
    } else if (drag.type === 'block') {
      els.svg.classList.add('is-dragging');
      api.state.positions.set(drag.key, { x: drag.origin.x + dx * k, y: drag.origin.y + dy * k });
      scheduleRedraw();
    }
  }

  function onPointerUp(event) {
    if (!drag) return;
    var done = drag;
    drag = null;
    els.svg.classList.remove('is-panning', 'is-dragging');
    if (els.svg.hasPointerCapture(event.pointerId)) els.svg.releasePointerCapture(event.pointerId);
    if (done.moved) return;
    var type = done.type === 'view' ? (done.band ? 'band' : 'background') : done.type;
    if (tap({ type: type, key: done.key || null, port: done.port || null, keyboard: false })) {
      return;
    }
    if (done.type === 'block' && done.key.indexOf('group:') === 0) toggleGroup(done.key, true);
    else if (done.type === 'frame') toggleGroup(done.key, false);
  }

  function tap(info) {
    return api.onTap.some(function (fn) { return fn(info); });
  }

  function toggleGroup(key, expand) {
    if (expand) api.state.expanded.add(key); else api.state.expanded.delete(key);
    api.state.selectedEdge = null;
    redraw();
    var target = els.svg.querySelector((expand ? '.fm-frame' : '.fm-block')
      + '[data-key="' + key + '"]');
    if (target) target.focus({ preventScroll: true });
  }

  function onKeyDown(event) {
    if (event.key === 'Escape') { closeMenu(); return; }
    if (event.key !== 'Enter' && event.key !== ' ') return;
    var target = event.target;
    var classes = target.classList;
    if (!classes) return;
    if (classes.contains('fm-block__menu')) {
      event.preventDefault();
      var rect = target.getBoundingClientRect();
      openMenu(target.closest('.fm-block').dataset.key, rect.left, rect.bottom);
      return;
    }
    var info = null;
    if (classes.contains('fm-port')) {
      info = { type: 'port', key: target.closest('.fm-block').dataset.key,
        port: target.dataset.port };
    } else if (classes.contains('fm-block')) {
      info = { type: 'block', key: target.dataset.key };
    } else if (classes.contains('fm-frame')) {
      info = { type: 'frame', key: target.dataset.key };
    } else if (classes.contains('fm-edge')) {
      info = { type: 'edge', key: target.dataset.key };
    }
    if (!info) return;
    event.preventDefault();
    info.keyboard = true;
    info.port = info.port || null;
    if (tap(info)) return;
    if (classes.contains('fm-block--group')) toggleGroup(target.dataset.key, true);
    else if (classes.contains('fm-frame')) toggleGroup(target.dataset.key, false);
  }

  // ── Menu « ⋯ » d'un bloc ─────────────────────────────────────────────────
  var menuKey = null;

  function openMenu(key, clientX, clientY) {
    var node = nodeOf(key);
    if (!node) return;
    var actions = api.menuActions.filter(function (a) { return a.visible(node); });
    if (!actions.length) return;
    menuKey = key;
    els.menu.textContent = '';
    actions.forEach(function (action) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'flow-map__menu-item';
      button.setAttribute('role', 'menuitem');
      button.textContent = action.label;
      button.addEventListener('click', function () {
        closeMenu();
        action.run(node);
      });
      els.menu.appendChild(button);
    });
    var board = els.board.getBoundingClientRect();
    els.menu.style.left = Math.round(clientX - board.left) + 'px';
    els.menu.style.top = Math.round(clientY - board.top) + 'px';
    els.menu.hidden = false;
    els.menu.querySelector('button').focus();
  }

  function closeMenu() {
    if (!els.menu || els.menu.hidden) return;
    els.menu.hidden = true;
    var trigger = menuKey && els.svg.querySelector(
      '.fm-block[data-key="' + menuKey + '"] .fm-block__menu');
    menuKey = null;
    if (trigger && els.menu.contains(document.activeElement)) trigger.focus();
  }

  function onClick(event) {
    var trigger = event.target.closest('.fm-block__menu');
    if (trigger) {
      openMenu(trigger.closest('.fm-block').dataset.key, event.clientX, event.clientY);
    }
  }

  function onContextMenu(event) {
    var block = event.target.closest('.fm-block');
    if (!block) return;
    event.preventDefault();
    openMenu(block.dataset.key, event.clientX, event.clientY);
  }

  function hideBlock(node) {
    api.state.hidden.add(node.key);
    api.state.expanded.delete(node.key);
    api.state.selectedEdge = null;
    redraw();
  }

  // ── Initialisation ───────────────────────────────────────────────────────
  function bindYear() {
    els.year.addEventListener('change', function () {
      if (target) load(target.companyId, parseInt(els.year.value, 10));
    });
    els.yearForm.addEventListener('submit', function (event) {
      event.preventDefault();
      var year = parseInt(els.yearOther.value, 10);
      if (!target || !els.yearOther.checkValidity() || !year) return;
      load(target.companyId, year);
    });
  }

  function bindBoard() {
    els.svg.addEventListener('wheel', onWheel, { passive: false });
    els.svg.addEventListener('pointerdown', onPointerDown);
    els.svg.addEventListener('pointermove', onPointerMove);
    els.svg.addEventListener('pointerup', onPointerUp);
    els.svg.addEventListener('pointercancel', onPointerUp);
    els.svg.addEventListener('click', onClick);
    els.svg.addEventListener('contextmenu', onContextMenu);
    els.svg.addEventListener('keydown', onKeyDown);
    els.menu.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', function (event) {
      if (!els.menu.contains(event.target) && !els.svg.contains(event.target)) closeMenu();
    });
    window.addEventListener('resize', onResize);
    // Le panneau latéral rétrécit le plateau : garder l'échelle de la vue.
    if (window.ResizeObserver) new ResizeObserver(onResize).observe(els.svg);
    document.addEventListener('flowmap:changed', function () { reload(); });
    els.fit.addEventListener('click', fitView);
    els.chip.addEventListener('click', function () {
      api.state.hidden.clear();
      redraw();
    });
  }

  function init() {
    var root = document.getElementById('flow-map');
    if (!root) return;
    els = {
      board: document.getElementById('flow-map-board'),
      svg: document.getElementById('flow-map-svg'),
      empty: document.getElementById('flow-map-empty'),
      menu: document.getElementById('flow-map-menu'),
      chip: document.getElementById('flow-map-hidden-chip'),
      fit: document.getElementById('flow-map-fit'),
      year: document.getElementById('flow-map-year'),
      yearForm: document.getElementById('flow-map-year-form'),
      yearOther: document.getElementById('flow-map-year-other'),
    };
    api.svg = els.svg;
    els.svg.setAttribute('tabindex', '-1');   // repli du focus quand le panneau se ferme
    api.rules = readJson('flow-rules') || {};
    api.kinds = readJson('flow-kinds') || [];
    api.canEdit = root.dataset.canEdit === '1';
    api.menuActions.push({
      id: 'hide',
      label: gettext('Masquer'),
      visible: function (node) { return node.key !== 'company:' + current.company.id; },
      run: hideBlock,
    });
    bindBoard();
    bindYear();

    var companies = readJson('companies-data') || [];
    var initial = readJson('initial-data');
    if (!initial) return;
    var saved = CompanyCombobox.savedId(companies);
    var combobox = CompanyCombobox.init({
      root: document.getElementById('company-combobox'),
      companies: companies,
      selected: { company_id: initial.company.id, company_name: initial.company.name },
      onSelect: function (id) { load(id, null); },
      persist: true,
    });
    if (saved && saved !== initial.company.id) {
      var company = companies.find(function (c) { return c.id === saved; });
      if (combobox) combobox.setSelected(company.id, company.name);
      load(saved, null);
    } else {
      show(initial);
    }
  }

  document.addEventListener('DOMContentLoaded', init);
  return api;
})();
