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
//   FlowMap.reload()     recharge l'entreprise et la plage affichées, sans recadrer
//   FlowMap.load(id, r)  charge une entreprise sur une plage r = {start, end}
//                        (r null : plage par défaut du périmètre)
//   FlowMap.includeYear(y) élargit la plage demandée pour qu'elle contienne y (avant reload)
//   FlowMap.range()      plage affichée {start, end} (ou null)
//   FlowMap.menuActions  entrées du menu « ⋯ » d'un bloc :
//                        {id, label: string, visible(node): bool, run(node)}
//   FlowMap.onRender     fonctions appelées après chaque dessin, avec le résultat
//   FlowMap.onTap        fonctions appelées pour un clic sans glisser (ou Entrée) :
//                        fn({type, key, port, keyboard}) -> true si traité (le
//                        comportement par défaut, déplier / replier, est alors sauté).
//                        type : 'block', 'frame', 'edge', 'port', 'band', 'background'
//                        (pour 'band', key vaut 'environment' ou 'market')
//   FlowMap.lastRender() dernier résultat de FlowMapDraw.render (ou null)
//   FlowMap.addSessionBlock({key, type, id, name}) -> 'added' | 'exists' | null
//                        bloc extérieur ajouté pour la session (colonne 0, rien en
//                        base) ; 'exists' : déjà sur la carte, il est montré (reveal)
//   FlowMap.removeSessionBlock(key), FlowMap.isSession(key)
//   FlowMap.reveal(key)  réaffiche le bloc (masqué, membre d'un groupe replié),
//                        l'amène dans la vue, le fait clignoter et focalise son « ⋯ »
// Blocs de session : gardés au rechargement de la même entreprise et de la même
// plage, oubliés sinon, et retirés dès que le serveur renvoie la même clé.
// Plage : « De » / « À » de la barre d'outils. Tant qu'on n'en a pas choisi, chaque
// entreprise s'ouvre sur sa plage par défaut ; une plage choisie est gardée quand
// on change d'entreprise (session de la page). Légende : chaque nature se masque
// ou se réaffiche (state.hiddenKinds), y compris d'une entreprise à l'autre.
// Événements sur document : « flowmap:loaded » (detail : données) après chaque
// chargement ; « flowmap:cleared » quand un chargement échoue et vide la carte ;
// « flowmap:changed », émis après une écriture, recharge la carte.
window.FlowMap = (function () {
  var MIN_SCALE = 0.2;        // unités SVG par pixel écran (zoom avant maximal)
  var MAX_SCALE = 6;          // zoom arrière maximal
  var MAX_FIT_SCALE = 1.5;    // cadrage initial : au-delà, texte illisible, on déplace la vue
  var DRAG_THRESHOLD = 4;
  var FLASH_MS = 1600;
  var YEAR_MIN = 1900;        // bornes des années (YEAR_MIN / YEAR_MAX côté serveur)
  var YEAR_MAX = 2100;

  var api = {
    state: {
      expanded: new Set(), hidden: new Set(), hiddenKinds: new Set(), positions: new Map(),
      selectedEdge: null, selectedBlock: null,
    },
    rules: {},
    kinds: [],
    canEdit: false,
    svg: null,
    menuActions: [],
    onRender: [],
    onTap: [],
    model: function () { return current; },
    includeYear: includeYear,
    range: function () { return current ? { start: current.start, end: current.end } : null; },
    lastRender: function () { return last; },
    redraw: redraw,
    reload: function () { return reload(); },
    load: load,
    addSessionBlock: addSessionBlock,
    removeSessionBlock: removeSessionBlock,
    isSession: isSession,
    reveal: reveal,
  };

  var current = null;
  var target = null;          // dernière demande {companyId, range} (affichée ou en cours)
  var chosen = null;          // plage choisie dans la barre d'outils {start, end}, ou null
  var request = 0;            // numéro de la dernière demande : seule elle est affichée
  var pending = null;         // AbortController de la demande en cours
  var last = null;            // dernier résultat de FlowMapDraw.render
  var view = null;            // viewBox {x, y, width, height}
  var viewPx = null;          // taille en pixels pour laquelle `view` a été calculée
  var frame = 0;
  var els = {};
  var session = { companyId: null, start: null, end: null, blocks: [] };

  function readJson(id) {
    var node = document.getElementById(id);
    return node ? JSON.parse(node.textContent) : null;
  }

  function resetState() {
    api.state.expanded.clear();
    api.state.hidden.clear();
    api.state.positions.clear();
    api.state.selectedEdge = null;
    api.state.selectedBlock = null;
    api.state.trace = null;
  }

  // ── Chargement ───────────────────────────────────────────────────────────
  // Une demande plus récente annule la précédente : une réponse lente ne peut
  // pas remplacer la carte demandée ensuite. `keepView` garde le cadrage (après
  // une écriture) ; sinon la carte est recadrée.
  function load(companyId, range, keepView) {
    var url = FlowMapUI.idUrl(FLOW_MAP_API_URL, companyId);
    if (range) url += FlowMapUI.rangeQuery(range.start, range.end);
    if (pending) pending.abort();
    var controller = new AbortController();
    var mine = ++request;
    pending = controller;
    target = { companyId: companyId, range: range || null };
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

  // `target` est la dernière demande (en cours ou affichée) : un rechargement ne
  // revient pas sur un changement d'entreprise ou de plage encore en route. La vue
  // n'est gardée que pour l'entreprise affichée.
  function reload() {
    if (!target) return null;
    var keepView = !!current && current.company.id === target.companyId;
    return load(target.companyId, target.range, keepView);
  }

  // Élargit la plage demandée à `year` : un élément enregistré hors de [De, À]
  // reste visible au rechargement. Sans effet si l'année est déjà dans la plage.
  function includeYear(year) {
    if (!target || !target.range || !isFinite(year)) return;
    var range = { start: Math.min(target.range.start, year), end: Math.max(target.range.end, year) };
    target = { companyId: target.companyId, range: range };
    if (chosen) chosen = { start: range.start, end: range.end };
  }

  function show(data, keepView) {
    mergeSession(data);
    current = data;
    target = { companyId: data.company.id, range: { start: data.start, end: data.end } };
    api.canEdit = !!data.can_edit;
    api.state.editable = api.canEdit;
    closeMenu();
    renderRange(data);
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
    document.dispatchEvent(new CustomEvent('flowmap:cleared'));
  }

  function showMessage(message) {
    els.empty.textContent = message;
    els.empty.hidden = false;
  }

  // ── Blocs de session ─────────────────────────────────────────────────────
  // Ajoutés depuis la barre d'outils sans rien écrire en base (pays, région,
  // entreprise, actif non détenu) : ils attendent leur premier flux.
  function mergeSession(data) {
    if (session.companyId !== data.company.id || session.start !== data.start
        || session.end !== data.end) {
      session = { companyId: data.company.id, start: data.start, end: data.end, blocks: [] };
    }
    var known = new Set(data.blocks.map(function (b) { return b.key; }));
    session.blocks = session.blocks.filter(function (b) { return !known.has(b.key); });
    session.blocks.forEach(function (b) { data.blocks.push(Object.assign({}, b)); });
  }

  function isSession(key) {
    return session.blocks.some(function (b) { return b.key === key; });
  }

  function findBlock(key) {
    if (!current) return null;
    return current.blocks.find(function (b) { return b.key === key; })
      || current.groups.find(function (g) { return g.key === key; }) || null;
  }

  function addSessionBlock(block) {
    if (!current) return null;
    if (findBlock(block.key)) {
      reveal(block.key);
      return 'exists';
    }
    var entry = {
      key: block.key, type: block.type, id: block.id, name: block.name, owned: false,
      group: null, column: 0, session: true,
    };
    session.blocks.push(entry);
    current.blocks.push(Object.assign({}, entry));
    redraw();
    reveal(block.key);
    return 'added';
  }

  function removeSessionBlock(key) {
    if (!current || !isSession(key)) return;
    session.blocks = session.blocks.filter(function (b) { return b.key !== key; });
    current.blocks = current.blocks.filter(function (b) { return b.key !== key; });
    api.state.hidden.delete(key);
    api.state.positions.delete(key);
    redraw();
  }

  // Montre un bloc : réaffiché s'il était masqué, groupe déplié s'il en est
  // membre, vue déplacée s'il est hors cadre ; il clignote et son « ⋯ » prend
  // le focus (repère pour la suite au clavier).
  function reveal(key) {
    var block = findBlock(key);
    if (!block || !view) return false;
    api.state.hidden.delete(key);
    if (block.group) {
      api.state.hidden.delete(block.group);
      api.state.expanded.add(block.group);
    }
    redraw();
    var node = nodeOf(key);
    if (!node) return false;
    var w = FlowMapDraw.BLOCK_W;
    var h = FlowMapDraw.BLOCK_H;
    var inside = node.x >= view.x && node.y >= view.y && node.x + w <= view.x + view.width
      && node.y + h <= view.y + view.height;
    if (!inside) {
      view.x = node.x + w / 2 - view.width / 2;
      view.y = node.y + h / 2 - view.height / 2;
      applyView();
    }
    var g = els.svg.querySelector('.fm-block[data-key="' + FlowMapUI.cssEscape(key) + '"]');
    if (!g) return false;
    g.classList.add('is-flash');
    setTimeout(function () { g.classList.remove('is-flash'); }, FLASH_MS);
    var focusEl = g.querySelector('.fm-block__menu') || (g.hasAttribute('tabindex') ? g : null);
    if (focusEl) focusEl.focus({ preventScroll: true });
    return true;
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
    var masked = current.flows.some(function (f) { return api.state.hiddenKinds.has(f.kind); });
    if (masked && !last.edges.length
        && current.flows.every(function (f) { return api.state.hiddenKinds.has(f.kind); })) {
      showMessage(gettext('Toutes les natures de flux sont masquées.'));
      return;
    }
    var empty = !last.edges.length && !masked && last.nodes.length <= 1;
    if (!empty) { els.empty.hidden = true; return; }
    var message;
    if (current.start === current.end) {
      message = api.canEdit
        ? gettext('Aucun flux pour %(year)s. Ajoutez un bloc pour commencer la carte.')
        : gettext('Aucun flux enregistré pour %(year)s.');
    } else {
      message = api.canEdit
        ? gettext('Aucun flux de %(start)s à %(end)s. Ajoutez un bloc pour commencer la carte.')
        : gettext('Aucun flux enregistré de %(start)s à %(end)s.');
    }
    showMessage(interpolate(message, {
      year: String(current.end), start: String(current.start), end: String(current.end),
    }, true));
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

  // ── Plage d'années ───────────────────────────────────────────────────────
  // Années proposées (datalist) et bornes affichées ; la saisie reste libre. Le
  // champ en cours de saisie n'est pas réécrit (« De » change au passage vers « À »,
  // dont la saisie ne doit pas être effacée par la réponse).
  function renderRange(data) {
    els.years.textContent = '';
    data.years.slice().sort(function (a, b) { return b - a; }).forEach(function (year) {
      var option = document.createElement('option');
      option.value = String(year);
      els.years.appendChild(option);
    });
    [[els.start, data.start], [els.end, data.end]].forEach(function (pair) {
      if (document.activeElement !== pair[0]) pair[0].value = String(pair[1]);
    });
    rangeError(null);
  }

  function rangeError(message) {
    els.rangeError.textContent = message || '';
    els.rangeError.hidden = !message;
    [els.start, els.end].forEach(function (input) {
      if (message) input.setAttribute('aria-invalid', 'true');
      else input.removeAttribute('aria-invalid');
    });
  }

  function readYear(input) {
    var text = input.value.trim();
    if (!/^[0-9]{4}$/.test(text)) return null;
    var year = parseInt(text, 10);
    return year >= YEAR_MIN && year <= YEAR_MAX ? year : null;
  }

  // Plage saisie : contrôlée ici (bornes, De ≤ À), sans requête si elle est fausse.
  function applyRange() {
    if (!target) return;
    var start = readYear(els.start);
    var end = readYear(els.end);
    if (start === null || end === null) {
      rangeError(interpolate(gettext('Saisissez des années entre %(min)s et %(max)s.'),
        { min: String(YEAR_MIN), max: String(YEAR_MAX) }, true));
      return;
    }
    if (start > end) {
      rangeError(gettext('L’année « De » doit précéder l’année « À » ou lui être égale.'));
      return;
    }
    rangeError(null);
    chosen = { start: start, end: end };
    var asked = target.range;
    if (asked && asked.start === start && asked.end === end) return;
    load(target.companyId, chosen);
  }

  // ── Légende : masquer / réafficher les flèches d'une nature ──────────────
  function toggleKind(button) {
    var kind = button.dataset.kind;
    var hidden = api.state.hiddenKinds;
    if (hidden.has(kind)) hidden.delete(kind); else hidden.add(kind);
    var off = hidden.has(kind);
    button.setAttribute('aria-pressed', off ? 'false' : 'true');
    button.classList.toggle('is-off', off);
    if (!current) return;
    var selected = api.state.selectedEdge;
    if (off && selected && selected.split('|')[2] === kind) {
      // La flèche ouverte n'est plus dessinée : fermer sa fiche sans enregistrer.
      if (window.FlowMapPanel) window.FlowMapPanel.close({ focus: false });
      api.state.selectedEdge = null;
    }
    redraw();
  }

  // ── Vue : cadrage, zoom, déplacement ─────────────────────────────────────
  function applyView() {
    viewPx = size();
    els.svg.setAttribute('viewBox', [view.x, view.y, view.width, view.height].join(' '));
    stretchBand();
  }

  // Les bandeaux (milieu, marché global) couvrent toute la largeur visible, leur
  // titre reste à l'écran.
  function stretchBand() {
    if (!view || !last) return;
    var left = Math.min(view.x, last.bounds.x);
    var right = Math.max(view.x + view.width, last.bounds.x + last.bounds.width);
    els.svg.querySelectorAll('.fm-band').forEach(function (band) {
      var rect = band.querySelector('.fm-band__rect');
      rect.setAttribute('x', left);
      rect.setAttribute('width', right - left);
      band.querySelector('.fm-band__label').setAttribute('x', view.x + 16);
    });
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
      var band = event.target.closest('.fm-band');
      drag = {
        type: 'view', start: start, origin: { x: view.x, y: view.y },
        band: band ? band.dataset.key : null,
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
    var key = done.type === 'view' ? done.band : done.key;
    if (tap({ type: type, key: key || null, port: done.port || null, keyboard: false })) {
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
  function bindToolbar() {
    [els.start, els.end].forEach(function (input) {
      input.addEventListener('change', applyRange);
      input.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        applyRange();
      });
    });
    els.range.addEventListener('submit', function (event) {
      event.preventDefault();
      applyRange();
    });
    els.legend.querySelectorAll('[data-kind]').forEach(function (button) {
      button.addEventListener('click', function () { toggleKind(button); });
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
      range: document.getElementById('flow-map-range'),
      start: document.getElementById('flow-map-start'),
      end: document.getElementById('flow-map-end'),
      years: document.getElementById('flow-map-years'),
      rangeError: document.getElementById('flow-map-range-error'),
      legend: document.getElementById('flow-map-legend'),
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
    bindToolbar();

    var companies = readJson('companies-data') || [];
    var initial = readJson('initial-data');
    if (!initial) return;
    var saved = CompanyCombobox.savedId(companies);
    var combobox = CompanyCombobox.init({
      root: document.getElementById('company-combobox'),
      companies: companies,
      selected: { company_id: initial.company.id, company_name: initial.company.name },
      onSelect: function (id) { load(id, chosen); },
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
