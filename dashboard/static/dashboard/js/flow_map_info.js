'use strict';

// Panneau d'information de la carte des flux, pour tous les visiteurs.
//
//   Clic (ou Entrée) sur un actif, une entreprise, un pays ou une région : sa fiche
//   (pays, région, détentions et vue satellite d'un actif ; identifiants et actifs
//   détenus d'une entreprise ; pays d'une région), puis ses flux entrants et
//   sortants tels que dessinés sur la carte. Les autres courbes sont atténuées
//   (FlowMap.state.selectedBlock). Un nouveau clic sur le bloc ferme la fiche.
//   Un flux de la liste ouvre son panneau : FlowMapPanel pour un Créateur, sinon
//   une fiche en lecture seule ici même (avec retour à la fiche du bloc).
//   Clic sur une flèche sans droit d'écriture : la même fiche en lecture seule.
//   Échap, ✕ ou clic sur le fond : fermeture. Pendant un tracé de flux, les clics
//   restent à FlowMapPanel.
//
//   FlowMapInfo.openBlock(key, opts)     fiche d'un bloc dessiné (opts.focus === false :
//                                        le focus reste où il est) -> bool
//   FlowMapInfo.openEdge(edge, flowId, fromBlock)  flux en lecture seule ; fromBlock :
//                                        bloc dont la fiche propose le retour
//   FlowMapInfo.close(opts)              ferme (opts.focus === false : idem)
// Ouvrir ce panneau émet « flowmap:panelopen » (detail : {panel: 'info'}) ; il se
// ferme quand un autre panneau s'ouvre. Doit être chargé avant flow_map_panel.js :
// son FlowMap.onTap passe en premier (il ferme la fiche quand un tracé commence).
window.FlowMapInfo = (function () {
  var ENV = 'environment';
  var MARKET = 'market';
  var INFO_TYPES = ['asset', 'company', 'country', 'region'];
  var MAP_ZOOM = 14;

  var els = {};
  var url = '';
  var mode = null;        // 'block' | 'edge' | null (fermé)
  var blockKey = null;    // bloc de la fiche, ou bloc d'où l'on a ouvert le flux
  var edgeKey = null;     // flèche affichée en lecture seule
  var opener = null;      // sélecteur de l'élément de la carte à refocaliser
  var request = 0;        // seule la dernière demande de fiche est affichée
  var map = null;
  var marker = null;

  // ── Utilitaires ──────────────────────────────────────────────────────────
  var attr = FlowMapUI.cssEscape;

  function node(tag, className, content) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (content !== undefined && content !== null) element.textContent = content;
    return element;
  }

  function typeOf(key) {
    return String(key).split(':')[0];
  }

  function typeLabel(type) {
    switch (type) {
      case 'asset': return gettext('Actif');
      case 'company': return gettext('Entreprise');
      case 'country': return gettext('Pays');
      case 'region': return gettext('Région');
      default: return '';
    }
  }

  function kindLabel(kind) {
    var found = FlowMap.kinds.find(function (k) { return k.value === kind; });
    return found ? found.label : kind;
  }

  function kindRank(kind) {
    var index = FlowMap.kinds.findIndex(function (k) { return k.value === kind; });
    return index < 0 ? FlowMap.kinds.length : index;
  }

  // Nom d'une extrémité : bandeau, bloc ou groupe de la carte.
  function endName(key) {
    if (key === ENV) return gettext('Environnement');
    if (key === MARKET) return gettext('Marché global');
    var model = FlowMap.model();
    var found = model && model.blocks.concat(model.groups || []).find(function (b) {
      return b.key === key;
    });
    return found ? found.name : key;
  }

  function quantity(value) {
    return FlowMapUI.compact(value);
  }

  function exactQuantity(flow) {
    return interpolate(gettext('Valeur exacte : %(value)s %(unit)s'),
      { value: FlowMapUI.exact(flow.quantity), unit: flow.what.unit }, true);
  }

  function percent(share) {
    return interpolate(gettext('%(value)s %'), {
      value: (share * 100).toLocaleString(APP_LOCALE, { maximumFractionDigits: 2 }),
    }, true);
  }

  function years(start, end) {
    if (start !== null && end !== null) {
      return start === end ? String(start)
        : interpolate(gettext('%(start)s – %(end)s'), { start: start, end: end }, true);
    }
    if (start !== null) return interpolate(gettext('depuis %(year)s'), { year: start }, true);
    if (end !== null) return interpolate(gettext('jusqu’en %(year)s'), { year: end }, true);
    return gettext('sans limite de date');
  }

  function flowText(flow) {
    var names = (flow.modifiers || []).map(function (m) { return m.name; });
    return flow.what.name + (names.length ? ' (' + names.join(', ') + ')' : '') + ' · '
      + quantity(flow.quantity) + ' ' + flow.what.unit + ' · ' + flow.year;
  }

  function findNode(key) {
    var result = FlowMap.lastRender();
    return result && result.nodes.find(function (n) { return n.key === key; });
  }

  function findEdge(key) {
    var result = FlowMap.lastRender();
    return result && result.edges.find(function (e) { return e.key === key; });
  }

  function blockSelector(key) {
    return '.fm-block[data-key="' + attr(key) + '"]';
  }

  function focusOpener() {
    var target = opener && FlowMap.svg.querySelector(opener);
    (target || FlowMap.svg).focus({ preventScroll: true });
  }

  // ── Panneau ──────────────────────────────────────────────────────────────
  function show(focus) {
    document.dispatchEvent(new CustomEvent('flowmap:panelopen', { detail: { panel: 'info' } }));
    els.panel.hidden = false;
    els.panel.scrollTop = 0;
    if (focus !== false) els.panel.focus();
  }

  function close(opts) {
    if (!mode) return;
    var hadFocus = els.panel.contains(document.activeElement);
    var wasEdge = mode === 'edge';
    mode = null;
    blockKey = null;
    edgeKey = null;
    request += 1;
    els.panel.hidden = true;
    FlowMap.state.selectedBlock = null;
    // Le flux ouvert depuis la fiche par un Créateur est sélectionné par FlowMapPanel :
    // on ne retire que la sélection posée ici.
    if (wasEdge) FlowMap.state.selectedEdge = null;
    FlowMap.redraw();
    if (hadFocus && !(opts && opts.focus === false)) focusOpener();
  }

  // ── Fiche d'un bloc ──────────────────────────────────────────────────────
  function openBlock(key, opts) {
    var target = findNode(key);
    if (!target || INFO_TYPES.indexOf(target.type) < 0) return false;
    var fresh = mode !== 'block' || blockKey !== key;
    show(opts && opts.focus === false ? false : true);
    mode = 'block';
    blockKey = key;
    edgeKey = null;
    opener = blockSelector(key);
    els.type.textContent = typeLabel(target.type);
    els.title.textContent = target.name;
    els.back.hidden = true;
    els.block.hidden = false;
    els.edge.hidden = true;
    if (fresh) {
      els.details.textContent = '';
      els.mapSection.hidden = true;
    }
    FlowMap.state.selectedEdge = null;
    FlowMap.state.selectedBlock = key;
    FlowMap.redraw();   // onRender remplit la liste des flux
    loadDetails(key);
    return true;
  }

  function loadDetails(key) {
    var mine = ++request;
    els.status.textContent = gettext('Chargement…');
    FlowMapUI.getJson(url + '?key=' + encodeURIComponent(key))
      .then(function (res) {
        if (mine !== request || mode !== 'block' || blockKey !== key) return;
        if (!res.ok) {
          var errors = (res.data && res.data.errors && res.data.errors.__all__) || [];
          els.status.textContent = errors[0] || gettext('Impossible de charger la fiche.');
          return;
        }
        els.status.textContent = '';
        renderDetails(res.data);
      })
      .catch(function () {
        if (mine === request) els.status.textContent = gettext('Impossible de charger la fiche.');
      });
  }

  function facts(pairs) {
    var dl = node('dl', 'fm-info__facts');
    pairs.forEach(function (pair) {
      if (!pair[1]) return;
      dl.appendChild(node('dt', null, pair[0]));
      dl.appendChild(node('dd', null, pair[1]));
    });
    return dl.childNodes.length ? dl : null;
  }

  function section(title, content) {
    var box = node('section', 'fm-info__section');
    box.appendChild(node('h3', 'fm-info__heading-sm', title));
    box.appendChild(content);
    return box;
  }

  // Détentions : [nom, part, années], le nom en gras pour l'entreprise de la carte.
  function holdings(rows, headers, empty) {
    if (!rows.length) return node('p', 'fm-info__empty', empty);
    var table = node('table', 'fm-info__table');
    var head = table.createTHead().insertRow();
    headers.forEach(function (label) {
      var th = node('th', null, label);
      th.scope = 'col';
      head.appendChild(th);
    });
    var body = table.createTBody();
    rows.forEach(function (row) {
      var tr = body.insertRow();
      var name = tr.insertCell();
      name.appendChild(node(row.strong ? 'strong' : 'span', null, row.name));
      tr.insertCell().textContent = percent(row.share);
      tr.insertCell().textContent = years(row.start_year, row.end_year);
    });
    return table;
  }

  function renderDetails(data) {
    els.details.textContent = '';
    var add = function (element) { if (element) els.details.appendChild(element); };
    var focusCompany = FlowMap.model() ? FlowMap.model().company.id : null;
    if (data.type === 'asset') {
      add(facts([[gettext('Pays'), data.country], [gettext('Région'), data.region]]));
      add(section(gettext('Détention'), holdings(data.ownerships.map(function (o) {
        return {
          name: o.company, strong: o.company_id === focusCompany, share: o.share,
          start_year: o.start_year, end_year: o.end_year,
        };
      }), [gettext('Entreprise'), gettext('Part'), gettext('Années')],
      gettext('Aucune détention enregistrée.'))));
      showMap(data.latitude, data.longitude);
    } else if (data.type === 'company') {
      add(facts([[gettext('ISIN'), data.isin], [gettext('Ticker'), data.ticker]])
        || node('p', 'fm-info__empty', gettext('Aucun identifiant renseigné.')));
      add(section(gettext('Actifs détenus'), holdings(data.assets.map(function (o) {
        return {
          name: o.asset, strong: false, share: o.share,
          start_year: o.start_year, end_year: o.end_year,
        };
      }), [gettext('Actif'), gettext('Part'), gettext('Années')],
      gettext('Aucun actif détenu.'))));
    } else if (data.type === 'region') {
      add(facts([[gettext('Pays'), data.country]]));
    }
  }

  // Vue satellite centrée sur l'actif (même imagerie que les autres cartes du site).
  function showMap(lat, lng) {
    var ready = typeof maplibregl !== 'undefined' && typeof mapStyleFor === 'function';
    if (!ready || !isFinite(lat) || !isFinite(lng)) {
      els.mapSection.hidden = true;
      return;
    }
    els.mapSection.hidden = false;
    if (!map) {
      map = new maplibregl.Map({
        container: els.map,
        style: mapStyleFor('satellite'),
        center: [lng, lat],
        zoom: MAP_ZOOM,
        attributionControl: { compact: true },
      });
      // Attribution repliée : sinon elle couvre la moitié de la mini-carte.
      map.on('load', function () {
        var attrib = els.map.querySelector('.maplibregl-ctrl-attrib');
        if (attrib) attrib.classList.remove('maplibregl-compact-show');
      });
      marker = new maplibregl.Marker().setLngLat([lng, lat]).addTo(map);
      return;
    }
    map.resize();
    map.jumpTo({ center: [lng, lat], zoom: MAP_ZOOM });
    marker.setLngLat([lng, lat]);
  }

  // Flux du bloc d'après le dernier dessin : ceux des natures masquées n'y sont pas.
  function renderFlows(result) {
    var incoming = [];
    var outgoing = [];
    result.edges.forEach(function (edge) {
      var list = edge.to === blockKey ? incoming : edge.from === blockKey ? outgoing : null;
      if (!list) return;
      edge.flows.forEach(function (flow) { list.push({ flow: flow, edge: edge }); });
    });
    fillFlows(els.inList, els.inTitle, incoming, true);
    fillFlows(els.outList, els.outTitle, outgoing, false);
    els.hiddenKinds.hidden = !FlowMap.state.hiddenKinds.size;
  }

  function fillFlows(list, title, entries, incoming) {
    var n = entries.length;
    title.textContent = interpolate(incoming
      ? ngettext('Flux entrant (%(n)s)', 'Flux entrants (%(n)s)', n)
      : ngettext('Flux sortant (%(n)s)', 'Flux sortants (%(n)s)', n), { n: n }, true);
    list.textContent = '';
    if (!n) {
      list.appendChild(node('li', 'fm-info__empty', incoming
        ? gettext('Aucun flux entrant sur la plage affichée.')
        : gettext('Aucun flux sortant sur la plage affichée.')));
      return;
    }
    entries.sort(function (a, b) {
      return kindRank(a.flow.kind) - kindRank(b.flow.kind)
        || Math.abs(b.flow.quantity) - Math.abs(a.flow.quantity) || a.flow.id - b.flow.id;
    });
    entries.forEach(function (entry) {
      var flow = entry.flow;
      var other = endName(incoming ? flow.from : flow.to);
      var item = node('li');
      var button = node('button', 'fm-info__flow fm-info__flow--' + flow.kind.toLowerCase());
      button.type = 'button';
      button.title = exactQuantity(flow);
      var swatch = node('i', 'fm-info__swatch');
      swatch.setAttribute('aria-hidden', 'true');
      button.appendChild(swatch);
      var text = node('span', 'fm-info__flow-text');
      text.appendChild(node('span', 'fm-info__flow-main', flowText(flow)));
      text.appendChild(node('span', 'fm-info__flow-sub', interpolate(incoming
        ? gettext('%(kind)s · depuis %(name)s') : gettext('%(kind)s · vers %(name)s'),
      { kind: kindLabel(flow.kind), name: other }, true)));
      button.appendChild(text);
      button.addEventListener('click', function () { openFlow(entry); });
      item.appendChild(button);
      list.appendChild(item);
    });
  }

  function openFlow(entry) {
    if (FlowMap.canEdit && window.FlowMapPanel) {
      FlowMapPanel.openEdge(entry.edge, entry.flow.id);
      return;
    }
    openEdge(entry.edge, entry.flow.id, blockKey);
  }

  // ── Flux en lecture seule ────────────────────────────────────────────────
  function openEdge(edge, flowId, fromBlock) {
    var flow = edge.flows.find(function (f) { return f.id === flowId; }) || edge.flows[0];
    show(true);
    mode = 'edge';
    edgeKey = edge.key;
    blockKey = fromBlock || null;
    els.type.textContent = kindLabel(edge.kind);
    els.title.textContent = interpolate(gettext('%(from)s → %(to)s'),
      { from: endName(edge.from), to: endName(edge.to) }, true);
    els.back.hidden = !blockKey;
    if (blockKey) {
      els.back.textContent = interpolate(gettext('← Retour à %(name)s'),
        { name: endName(blockKey) }, true);
    }
    els.block.hidden = true;
    els.edge.hidden = false;
    renderEdgeFlows(edge, flow);
    renderFacts(flow);
    FlowMap.state.selectedBlock = null;
    FlowMap.state.selectedEdge = edge.key;
    FlowMap.redraw();
  }

  function renderEdgeFlows(edge, selected) {
    els.edgeList.textContent = '';
    els.edgeFlows.hidden = edge.flows.length < 2;
    if (edge.flows.length < 2) return;
    edge.flows.forEach(function (flow) {
      var label = node('label', 'fm-panel__flow');
      var input = node('input');
      input.type = 'radio';
      input.name = 'fm-info-flow';
      input.value = String(flow.id);
      input.checked = flow === selected;
      input.addEventListener('change', function () {
        if (input.checked) renderFacts(flow);
      });
      label.appendChild(input);
      label.appendChild(node('span', null, flowText(flow)));
      els.edgeList.appendChild(label);
    });
  }

  function renderFacts(flow) {
    var pairs = [
      [gettext('Nature'), kindLabel(flow.kind)],
      [gettext('Origine'), endName(flow.from)],
      [gettext('Destination'), endName(flow.to)],
      [gettext('Commodité'), flow.what.name],
      [gettext('Modificateurs'), (flow.modifiers || []).map(function (m) {
        return m.name;
      }).join(', ')],
      [gettext('Quantité'), quantity(flow.quantity) + ' ' + flow.what.unit],
      [gettext('Année'), String(flow.year)],
      [gettext('Tier'), String(flow.tier)],
      [gettext('Scope GES'), flow.scope !== 'undefined' ? flow.scope : ''],
      [gettext('Source'), flow.source],
      [gettext('Référence'), flow.reference],
    ];
    els.facts.textContent = '';
    pairs.forEach(function (pair) {
      if (!pair[1]) return;
      els.facts.appendChild(node('dt', null, pair[0]));
      var value = els.facts.appendChild(node('dd', null, pair[1]));
      if (pair[0] === gettext('Quantité')) value.title = exactQuantity(flow);
    });
  }

  // ── Carte ────────────────────────────────────────────────────────────────
  function onTap(info) {
    if (FlowMap.state.trace) return false;
    if (info.type === 'port') {
      // Un tracé ou une fiche de flux commence (FlowMapPanel) : la fiche se ferme.
      close({ focus: false });
      return false;
    }
    if (info.type === 'block') {
      if (INFO_TYPES.indexOf(typeOf(info.key)) < 0) return false;
      if (mode === 'block' && blockKey === info.key) {
        close();
        if (info.keyboard) focusOpener();
        return true;
      }
      return openBlock(info.key, { focus: info.keyboard });
    }
    if (info.type === 'edge') {
      if (FlowMap.canEdit) return false;   // FlowMapPanel ouvre la flèche
      var edge = findEdge(info.key);
      if (!edge) return false;
      opener = '.fm-edge[data-key="' + attr(edge.key) + '"]';
      openEdge(edge, null, null);
      return true;
    }
    if (info.type === 'background') close({ focus: false });
    return false;
  }

  // Après chaque dessin : liste des flux à jour (natures masquées…) ; fiche
  // fermée si son bloc ou sa flèche n'est plus dessiné (masqué, groupe replié).
  // Fermeture différée : elle redessine, ce qui ne peut se faire pendant un dessin.
  function onRender(result) {
    if (!mode || !result) return;
    var gone = mode === 'block'
      ? !result.nodes.some(function (n) { return n.key === blockKey; })
      : !result.edges.some(function (e) { return e.key === edgeKey; });
    if (gone) {
      Promise.resolve().then(function () { close({ focus: false }); });
      return;
    }
    if (mode === 'block') renderFlows(result);
  }

  function onEscape(event) {
    if (event.key !== 'Escape' || event.defaultPrevented || !mode) return;
    if (FlowMap.state.trace) return;   // Échap annule d'abord le tracé (FlowMapPanel)
    var dialog = document.getElementById('flow-map-confirm');
    if (dialog && dialog.open) return;
    event.preventDefault();
    close();
  }

  function init() {
    var panel = document.getElementById('flow-map-info');
    if (!panel || !window.FlowMap || !window.FLOW_MAP_BLOCK_URL) return;
    url = FLOW_MAP_BLOCK_URL;
    els = {
      panel: panel,
      type: document.getElementById('fm-info-type'),
      title: document.getElementById('fm-info-title'),
      closeButton: document.getElementById('fm-info-close'),
      back: document.getElementById('fm-info-back'),
      block: document.getElementById('fm-info-block'),
      status: document.getElementById('fm-info-status'),
      details: document.getElementById('fm-info-details'),
      mapSection: document.getElementById('fm-info-map-section'),
      map: document.getElementById('fm-info-map'),
      inTitle: document.getElementById('fm-info-in-title'),
      inList: document.getElementById('fm-info-in'),
      outTitle: document.getElementById('fm-info-out-title'),
      outList: document.getElementById('fm-info-out'),
      hiddenKinds: document.getElementById('fm-info-hidden-kinds'),
      edge: document.getElementById('fm-info-edge'),
      edgeFlows: document.getElementById('fm-info-edge-flows'),
      edgeList: document.getElementById('fm-info-edge-list'),
      facts: document.getElementById('fm-info-facts'),
    };
    els.closeButton.addEventListener('click', function () { close(); });
    els.back.addEventListener('click', function () {
      if (blockKey && !openBlock(blockKey)) close();
    });
    document.addEventListener('keydown', onEscape);
    document.addEventListener('flowmap:panelopen', function (event) {
      if (event.detail.panel !== 'info') close({ focus: false });
    });
    // Carte rechargée (écriture, autre plage) : la fiche suit son bloc s'il est
    // encore dessiné ; un flux en lecture seule se ferme.
    document.addEventListener('flowmap:loaded', function () {
      if (mode === 'block' && findNode(blockKey)) openBlock(blockKey, { focus: false });
      else close({ focus: false });
    });
    document.addEventListener('flowmap:cleared', function () { close({ focus: false }); });
    FlowMap.onTap.push(onTap);
    FlowMap.onRender.push(onRender);
  }

  document.addEventListener('DOMContentLoaded', init);

  return {
    openBlock: openBlock,
    openEdge: openEdge,
    close: close,
  };
})();
