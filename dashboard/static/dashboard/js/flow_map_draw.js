'use strict';

// Dessin SVG de la carte des flux (spec 2026-10-22 §4). Aucun fetch, aucun
// état global : l'état de la page vit dans flow_map.js, qui rappelle render().
//
//   FlowMapDraw.render(svg, model, state) -> {nodes, edges, bounds}
//     model  : réponse de build_flow_map (blocks, groups, flows, company, year…)
//     state  : {expanded: Set<groupKey>, hidden: Set<blockKey>,
//               positions: Map<key, {x, y}>, selectedEdge: string|null}
//     nodes  : blocs dessinés [{key, type, name, owned, column, x, y, …}]
//     edges  : courbes dessinées (aggregateEdges + width, label)
//     bounds : rectangle englobant {x, y, width, height}, pour cadrer la vue
//   FlowMapDraw.aggregateEdges(flows, model, state)
//     -> [{key, from, to, kind, flows: [flow], total}]
//   FlowMapDraw.curve(p0, p3, vertical) -> chemin « M… C… » (Bézier en S)
//
// Dans le SVG : chaque bloc est un <g class="fm-block" data-key>, chaque courbe
// un <g class="fm-edge" data-key>, le bandeau un <g class="fm-band"
// data-key="environment">, le cadre d'un groupe déplié un <g class="fm-frame">.
window.FlowMapDraw = (function () {
  var NS = 'http://www.w3.org/2000/svg';
  var ENV = 'environment';

  var BLOCK_W = 170;
  var BLOCK_H = 64;
  var COL_GAP = 120;          // espace horizontal entre deux colonnes
  var ROW_GAP = 36;           // espace vertical entre deux blocs
  var PAD = 40;
  var BAND_Y = 0;
  var BAND_H = 58;
  var TOP = BAND_Y + BAND_H + 80;   // première rangée de blocs, sous le bandeau
  var FRAME_HEAD = 30;        // place du titre d'un groupe déplié
  var FRAME_PAD = 12;
  var MIN_WIDTH = 1.5;
  var MAX_WIDTH = 12;
  var NAME_MAX = 20;
  var LABEL_MAX = 22;
  var TITLE_FLOWS_MAX = 12;
  var SWEEPS = 4;

  // ── Utilitaires ──────────────────────────────────────────────────────────
  function el(tag, attrs, parent) {
    var node = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (name) {
      if (attrs[name] !== null && attrs[name] !== undefined) node.setAttribute(name, attrs[name]);
    });
    if (parent) parent.appendChild(node);
    return node;
  }

  function text(tag, attrs, content, parent) {
    var node = el(tag, attrs, parent);
    node.textContent = content;
    return node;
  }

  function truncate(value, max) {
    var s = String(value);
    return s.length > max ? s.slice(0, max - 1) + '…' : s;
  }

  function pt(p) {
    return Math.round(p[0] * 10) / 10 + ',' + Math.round(p[1] * 10) / 10;
  }

  function quantity(n) {
    return Number(n).toLocaleString(APP_LOCALE, { maximumFractionDigits: 2 });
  }

  function kindClass(kind) {
    return String(kind).toLowerCase();
  }

  // ── Agrégation ───────────────────────────────────────────────────────────
  function indexModel(model) {
    var blocks = {};
    var groups = {};
    model.blocks.forEach(function (b) { blocks[b.key] = b; });
    (model.groups || []).forEach(function (g) { groups[g.key] = g; });
    return { blocks: blocks, groups: groups };
  }

  // Clé du nœud dessiné pour un bloc : le groupe s'il est replié, null si masqué.
  function resolver(state, idx) {
    return function (key) {
      if (key === ENV) return ENV;
      if (state.hidden.has(key)) return null;
      var block = idx.blocks[key];
      var node = block && block.group && !state.expanded.has(block.group) ? block.group : key;
      return state.hidden.has(node) ? null : node;
    };
  }

  // Une courbe par (origine, destination, nature), après substitution des
  // membres des groupes repliés ; les flux internes à un groupe replié disparaissent.
  function aggregateEdges(flows, model, state) {
    var resolve = resolver(state, indexModel(model));
    var byKey = new Map();
    flows.forEach(function (flow) {
      var from = resolve(flow.from);
      var to = resolve(flow.to);
      if (from === null || to === null || from === to) return;
      var key = from + '|' + to + '|' + flow.kind;
      var edge = byKey.get(key);
      if (!edge) {
        edge = { key: key, from: from, to: to, kind: flow.kind, flows: [], total: 0 };
        byKey.set(key, edge);
      }
      edge.flows.push(flow);
      edge.total += Math.abs(Number(flow.quantity) || 0);
    });
    var edges = Array.from(byKey.values());
    edges.forEach(function (edge) {
      edge.flows.sort(function (a, b) {
        return Math.abs(b.quantity) - Math.abs(a.quantity) || a.id - b.id;
      });
    });
    return edges;
  }

  // « Soja +2 » : commodité de plus forte quantité et nombre des autres.
  function edgeLabel(edge) {
    var byWhat = new Map();
    edge.flows.forEach(function (flow) {
      var entry = byWhat.get(flow.what.id) || { name: flow.what.name, total: 0 };
      entry.total += Math.abs(Number(flow.quantity) || 0);
      byWhat.set(flow.what.id, entry);
    });
    var sorted = Array.from(byWhat.values()).sort(function (a, b) {
      return b.total - a.total || a.name.localeCompare(b.name);
    });
    var name = truncate(sorted[0].name, LABEL_MAX);
    if (sorted.length === 1) return name;
    return interpolate(gettext('%(name)s +%(count)s'),
      { name: name, count: sorted.length - 1 }, true);
  }

  // Épaisseur bornée, proportionnelle à la quantité totale dans la vue.
  function edgeWidth(total, max) {
    if (!max) return MIN_WIDTH;
    return MIN_WIDTH + (MAX_WIDTH - MIN_WIDTH) * (total / max);
  }

  // ── Nœuds visibles ───────────────────────────────────────────────────────
  function visibleNodes(model, state, idx, edges) {
    var used = new Set();
    edges.forEach(function (e) { used.add(e.from); used.add(e.to); });
    var nodes = [];
    var seen = new Set();
    model.blocks.forEach(function (block) {
      if (block.group && !state.expanded.has(block.group)) {
        var group = idx.groups[block.group];
        if (!group || seen.has(group.key) || state.hidden.has(group.key)) return;
        seen.add(group.key);
        nodes.push({
          key: group.key, type: 'group', id: group.id, name: group.name, owned: group.owned,
          column: group.column, group: null, members: group.members.slice(),
        });
        return;
      }
      if (state.hidden.has(block.key)) return;
      if (block.type === 'unknown' && !used.has(block.key)) return;
      nodes.push(Object.assign({}, block));
    });
    return nodes;
  }

  // ── Rangement ────────────────────────────────────────────────────────────
  // Colonnes données par le serveur ; ordre vertical par barycentre des voisins
  // (balayages gauche → droite puis droite → gauche). Les membres d'un groupe
  // déplié restent contigus : ils forment une seule « unité » à ranger.
  function columnsOf(nodes) {
    var columns = new Map();
    nodes.forEach(function (node) {
      if (!columns.has(node.column)) columns.set(node.column, []);
      var units = columns.get(node.column);
      var unitKey = node.group || node.key;
      var unit = units.find(function (u) { return u.key === unitKey; });
      if (!unit) {
        unit = { key: unitKey, frame: !!node.group, nodes: [] };
        units.push(unit);
      }
      unit.nodes.push(node);
    });
    return Array.from(columns.keys()).sort(function (a, b) { return a - b; })
      .map(function (column) { return { column: column, units: columns.get(column) }; });
  }

  function rankPositions(columns) {
    var rank = new Map();
    columns.forEach(function (col) {
      var flat = [];
      col.units.forEach(function (u) { flat.push.apply(flat, u.nodes); });
      flat.forEach(function (node, i) { rank.set(node.key, i - (flat.length - 1) / 2); });
    });
    return rank;
  }

  function orderColumns(columns, nodes, edges) {
    var columnOf = new Map();
    nodes.forEach(function (n) { columnOf.set(n.key, n.column); });
    var neighbours = new Map();
    edges.forEach(function (e) {
      if (e.from === ENV || e.to === ENV) return;
      [[e.from, e.to], [e.to, e.from]].forEach(function (pair) {
        if (!neighbours.has(pair[0])) neighbours.set(pair[0], []);
        neighbours.get(pair[0]).push(pair[1]);
      });
    });

    function sweep(sequence, before) {
      sequence.forEach(function (col) {
        var rank = rankPositions(columns);
        var scored = col.units.map(function (unit, index) {
          var sum = 0;
          var count = 0;
          unit.nodes.forEach(function (node) {
            (neighbours.get(node.key) || []).forEach(function (other) {
              var c = columnOf.get(other);
              if (c === undefined || !before(c, col.column)) return;
              sum += rank.get(other);
              count += 1;
            });
          });
          var own = unit.nodes.reduce(function (s, n) { return s + rank.get(n.key); }, 0);
          return { unit: unit, index: index, score: count ? sum / count : own / unit.nodes.length };
        });
        scored.sort(function (a, b) { return a.score - b.score || a.index - b.index; });
        col.units = scored.map(function (s) { return s.unit; });
      });
    }

    var reversed = columns.slice().reverse();
    for (var i = 0; i < SWEEPS; i += 1) {
      sweep(columns, function (c, own) { return c < own; });
      sweep(reversed, function (c, own) { return c > own; });
    }
  }

  function unitHeight(unit) {
    var h = unit.nodes.length * BLOCK_H + (unit.nodes.length - 1) * ROW_GAP;
    return unit.frame ? h + FRAME_HEAD + FRAME_PAD : h;
  }

  function columnHeight(col) {
    return col.units.reduce(function (s, u) { return s + unitHeight(u); }, 0)
      + Math.max(col.units.length - 1, 0) * ROW_GAP;
  }

  function placeNodes(nodes, edges, state) {
    var columns = columnsOf(nodes);
    orderColumns(columns, nodes, edges);
    var tallest = columns.reduce(function (m, col) { return Math.max(m, columnHeight(col)); }, 0);
    columns.forEach(function (col) {
      var x = PAD + col.column * (BLOCK_W + COL_GAP);
      var y = TOP + (tallest - columnHeight(col)) / 2;
      col.units.forEach(function (unit) {
        if (unit.frame) y += FRAME_HEAD;
        unit.nodes.forEach(function (node) {
          node.x = x;
          node.y = y;
          y += BLOCK_H + ROW_GAP;
        });
        if (unit.frame) y += FRAME_PAD;
      });
    });
    nodes.forEach(function (node) {
      var moved = state.positions.get(node.key);
      if (moved) { node.x = moved.x; node.y = moved.y; }
    });
  }

  // ── Géométrie des courbes ────────────────────────────────────────────────
  function controls(p0, p3, vertical) {
    if (vertical) {
      var dy = (p3[1] - p0[1]) / 2;
      return [[p0[0], p0[1] + dy], [p3[0], p3[1] - dy]];
    }
    var dx = Math.max(Math.abs(p3[0] - p0[0]) / 2, 40);
    return [[p0[0] + dx, p0[1]], [p3[0] - dx, p3[1]]];
  }

  // Bézier cubique en S : points de contrôle à mi-distance horizontale (ou
  // verticale vers / depuis le bandeau du milieu, `vertical` vrai).
  function curve(p0, p3, vertical) {
    var c = controls(p0, p3, vertical);
    return 'M' + pt(p0) + ' C' + pt(c[0]) + ' ' + pt(c[1]) + ' ' + pt(p3);
  }

  function midpoint(p0, p3, vertical) {
    var c = controls(p0, p3, vertical);
    return [
      (p0[0] + 3 * c[0][0] + 3 * c[1][0] + p3[0]) / 8,
      (p0[1] + 3 * c[0][1] + 3 * c[1][1] + p3[1]) / 8,
    ];
  }

  // Points d'attache répartis sur un côté : `count` positions entre a et b.
  function slots(a, b, count) {
    var out = [];
    for (var i = 0; i < count; i += 1) out.push(a + (b - a) * (i + 1) / (count + 1));
    return out;
  }

  function anchorEdges(edges, byKey) {
    var sides = new Map();   // nodeKey -> {out: [], in: [], up: [], down: []}
    function side(key) {
      if (!sides.has(key)) sides.set(key, { out: [], in: [], up: [], down: [] });
      return sides.get(key);
    }
    function centerY(key) { return byKey.get(key).y + BLOCK_H / 2; }
    edges.forEach(function (e) {
      if (e.from === ENV) side(e.to).down.push(e);
      else if (e.to === ENV) side(e.from).up.push(e);
      else { side(e.from).out.push(e); side(e.to).in.push(e); }
    });
    sides.forEach(function (s, key) {
      var node = byKey.get(key);
      var stack = node.type === 'group' ? 8 : 0;   // pile de cartes : décalage haut-droite
      s.out.sort(function (a, b) { return centerY(a.to) - centerY(b.to); });
      s.in.sort(function (a, b) { return centerY(a.from) - centerY(b.from); });
      slots(node.y + 8, node.y + BLOCK_H - 8, s.out.length).forEach(function (y, i) {
        s.out[i].p0 = [node.x + BLOCK_W + stack, y];
      });
      slots(node.y + 8, node.y + BLOCK_H - 8, s.in.length).forEach(function (y, i) {
        s.in[i].p3 = [node.x, y];
      });
      // Haut du bloc : consommations à gauche, émissions et déchets à droite.
      slots(node.x + 12, node.x + BLOCK_W / 2 - 6, s.down.length).forEach(function (x, i) {
        s.down[i].p0 = [x, BAND_Y + BAND_H];
        s.down[i].p3 = [x, node.y - stack];
        s.down[i].slot = i;
      });
      slots(node.x + BLOCK_W / 2 + 6, node.x + BLOCK_W - 12, s.up.length).forEach(function (x, i) {
        s.up[i].p0 = [x, node.y - stack];
        s.up[i].p3 = [x, BAND_Y + BAND_H];
        s.up[i].slot = s.down.length + i;
      });
    });
    edges.forEach(function (e) { e.vertical = e.from === ENV || e.to === ENV; });
  }

  // Étiquette au milieu d'une courbe horizontale ; sur une verticale (droite),
  // à une hauteur qui varie d'une attache à l'autre pour ne pas se chevaucher.
  function labelPoint(edge, base) {
    if (!edge.vertical) {
      var mid = midpoint(edge.p0, base, false);
      return [mid[0], mid[1] - edge.width / 2 - 5];
    }
    var top = Math.min(edge.p0[1], edge.p3[1]);
    var bottom = Math.max(edge.p0[1], edge.p3[1]);
    return [edge.p0[0] + edge.width / 2 + 4, top + (bottom - top) * (0.3 + 0.2 * (edge.slot % 3))];
  }

  // ── Dessin ───────────────────────────────────────────────────────────────
  function flowLine(flow, edge, idx) {
    var line = flow.what.name + ' · ' + quantity(flow.quantity) + ' ' + flow.what.unit;
    var member = null;
    if (edge.from !== flow.from && idx.blocks[flow.from]) member = idx.blocks[flow.from].name;
    else if (edge.to !== flow.to && idx.blocks[flow.to]) member = idx.blocks[flow.to].name;
    return member ? line + ' (' + member + ')' : line;
  }

  function edgeTitle(edge, idx, names) {
    var lines = [interpolate(gettext('%(kind)s : %(from)s → %(to)s'), {
      kind: edge.flows[0].kind_label, from: names(edge.from), to: names(edge.to),
    }, true)];
    edge.flows.slice(0, TITLE_FLOWS_MAX).forEach(function (f) {
      lines.push(flowLine(f, edge, idx));
    });
    var rest = edge.flows.length - TITLE_FLOWS_MAX;
    if (rest > 0) {
      lines.push(interpolate(ngettext('… et %(n)s autre flux', '… et %(n)s autres flux', rest),
        { n: rest }, true));
    }
    return lines.join('\n');
  }

  function drawEdge(layer, edge, selected, title) {
    var w = edge.width;
    var vertical = edge.vertical;
    var dir = vertical ? [0, edge.p3[1] > edge.p0[1] ? 1 : -1] : [1, 0];
    var len = 5 + w * 0.9;
    var half = 3.5 + w * 0.75;
    var base = [edge.p3[0] - dir[0] * len, edge.p3[1] - dir[1] * len];
    var perp = [-dir[1], dir[0]];
    var d = curve(edge.p0, base, vertical);

    var g = el('g', {
      class: 'fm-edge fm-edge--' + kindClass(edge.kind) + (selected ? ' is-selected' : ''),
      'data-key': edge.key,
    }, layer);
    text('title', {}, title, g);
    el('path', { class: 'fm-edge__hit', d: d, 'stroke-width': w + 12 }, g);
    el('path', { class: 'fm-edge__line', d: d, 'stroke-width': w }, g);
    el('path', {
      class: 'fm-edge__arrow',
      d: 'M' + pt(edge.p3) + ' L' + pt([base[0] + perp[0] * half, base[1] + perp[1] * half])
        + ' L' + pt([base[0] - perp[0] * half, base[1] - perp[1] * half]) + ' Z',
    }, g);
    var at = labelPoint(edge, base);
    text('text', {
      class: 'fm-edge__label', x: Math.round(at[0]), y: Math.round(at[1]),
      'text-anchor': vertical ? 'start' : 'middle',
    }, edge.label, g);
  }

  function typeLabel(node) {
    switch (node.type) {
      case 'country': return gettext('Pays');
      case 'region': return gettext('Région');
      case 'company': return gettext('Entreprise');
      case 'asset': return gettext('Actif');
      case 'group':
        return interpolate(ngettext('Groupe · %(n)s actif', 'Groupe · %(n)s actifs',
          node.members.length), { n: node.members.length }, true);
      default: return '';
    }
  }

  function drawBlock(layer, node, focusKey) {
    var classes = ['fm-block', 'fm-block--' + node.type];
    if (node.owned) classes.push('is-owned');
    if (node.key === focusKey) classes.push('is-focus');
    var g = el('g', {
      class: classes.join(' '), 'data-key': node.key,
      transform: 'translate(' + pt([node.x, node.y]) + ')',
    }, layer);
    var type = typeLabel(node);
    text('title', {}, type ? type + ' — ' + node.name : node.name, g);
    if (node.type === 'group') {
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      g.setAttribute('aria-expanded', 'false');
      [8, 4].forEach(function (offset) {
        el('rect', { class: 'fm-block__stack', x: offset, y: -offset, width: BLOCK_W,
          height: BLOCK_H, rx: 8 }, g);
      });
    }
    el('rect', { class: 'fm-block__card', width: BLOCK_W, height: BLOCK_H, rx: 8 }, g);
    if (type) {
      text('text', { class: 'fm-block__type', x: 12, y: 22 }, type.toLocaleUpperCase(), g);
    }
    text('text', { class: 'fm-block__name', x: 12, y: type ? 46 : 38 },
      truncate(node.name, NAME_MAX), g);
    if (node.type === 'group') {
      text('text', { class: 'fm-block__toggle', x: 12, y: BLOCK_H - 4 },
        '▸ ' + gettext('déplier'), g);
    }
    if (node.key !== focusKey) {
      var menu = el('g', {
        class: 'fm-block__menu', 'data-action': 'menu', tabindex: '0', role: 'button',
        'aria-label': interpolate(gettext('Actions du bloc %(name)s'), { name: node.name }, true),
      }, g);
      el('circle', { cx: BLOCK_W - 16, cy: 17, r: 10 }, menu);
      text('text', { x: BLOCK_W - 16, y: 21, 'text-anchor': 'middle' }, '⋯', menu);
    }
  }

  function drawFrame(layer, group, members) {
    var minX = Infinity;
    var minY = Infinity;
    var maxX = -Infinity;
    var maxY = -Infinity;
    members.forEach(function (n) {
      minX = Math.min(minX, n.x); minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x + BLOCK_W); maxY = Math.max(maxY, n.y + BLOCK_H);
    });
    var box = {
      x: minX - FRAME_PAD, y: minY - FRAME_HEAD,
      width: maxX - minX + 2 * FRAME_PAD, height: maxY - minY + FRAME_HEAD + FRAME_PAD,
    };
    var g = el('g', {
      class: 'fm-frame' + (group.owned ? ' is-owned' : ''), 'data-key': group.key,
      tabindex: '0', role: 'button', 'aria-expanded': 'true',
    }, layer);
    text('title', {}, interpolate(gettext('Groupe %(name)s : cliquer pour replier'),
      { name: group.name }, true), g);
    el('rect', { class: 'fm-frame__rect', x: box.x, y: box.y, width: box.width,
      height: box.height, rx: 10 }, g);
    text('text', { class: 'fm-frame__label', x: box.x + 10, y: box.y + 19 },
      '▾ ' + truncate(group.name, NAME_MAX + 4) + ' · ' + gettext('replier'), g);
    return box;
  }

  function drawBand(layer, bounds) {
    var g = el('g', { class: 'fm-band', 'data-key': ENV }, layer);
    el('rect', { class: 'fm-band__rect', x: bounds.x, y: BAND_Y, width: bounds.width,
      height: BAND_H, rx: 10 }, g);
    text('text', { class: 'fm-band__label', x: bounds.x + 16, y: BAND_Y + 34 },
      gettext('Environnement — milieu naturel (eau, air, sol)'), g);
  }

  function computeBounds(nodes, frames) {
    var minX = PAD;
    var maxX = PAD + BLOCK_W;
    var maxY = TOP + BLOCK_H;
    nodes.forEach(function (n) {
      minX = Math.min(minX, n.x);
      maxX = Math.max(maxX, n.x + BLOCK_W + 8);   // + 8 : pile de cartes d'un groupe
      maxY = Math.max(maxY, n.y + BLOCK_H);
    });
    frames.forEach(function (b) {
      minX = Math.min(minX, b.x);
      maxX = Math.max(maxX, b.x + b.width);
      maxY = Math.max(maxY, b.y + b.height);
    });
    var x = minX - PAD;
    var y = BAND_Y - PAD / 2;
    return { x: x, y: y, width: maxX + PAD - x, height: maxY + PAD - y };
  }

  function render(svg, model, state) {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var idx = indexModel(model);
    var edges = aggregateEdges(model.flows, model, state);
    var nodes = visibleNodes(model, state, idx, edges);
    var byKey = new Map(nodes.map(function (n) { return [n.key, n]; }));
    edges = edges.filter(function (e) {
      return (e.from === ENV || byKey.has(e.from)) && (e.to === ENV || byKey.has(e.to));
    });
    placeNodes(nodes, edges, state);
    anchorEdges(edges, byKey);
    var max = edges.reduce(function (m, e) { return Math.max(m, e.total); }, 0);
    edges.forEach(function (e) {
      e.width = edgeWidth(e.total, max);
      e.label = edgeLabel(e);
    });

    function name(key) {
      if (key === ENV) return gettext('Environnement');
      var node = byKey.get(key);
      return node ? node.name : key;
    }

    var bandLayer = el('g', { class: 'fm-layer fm-layer--band' }, svg);
    var frameLayer = el('g', { class: 'fm-layer fm-layer--frames' }, svg);
    var edgeLayer = el('g', { class: 'fm-layer fm-layer--edges' }, svg);
    var blockLayer = el('g', { class: 'fm-layer fm-layer--blocks' }, svg);

    var frames = [];
    (model.groups || []).forEach(function (group) {
      if (!state.expanded.has(group.key) || state.hidden.has(group.key)) return;
      var members = nodes.filter(function (n) { return n.group === group.key; });
      if (members.length) frames.push(drawFrame(frameLayer, group, members));
    });
    var bounds = computeBounds(nodes, frames);
    drawBand(bandLayer, bounds);

    edges.forEach(function (e) {
      drawEdge(edgeLayer, e, e.key === state.selectedEdge, edgeTitle(e, idx, name));
    });
    var focusKey = 'company:' + model.company.id;
    nodes.forEach(function (n) { drawBlock(blockLayer, n, focusKey); });

    return { nodes: nodes, edges: edges, bounds: bounds };
  }

  return {
    render: render,
    aggregateEdges: aggregateEdges,
    curve: curve,
    edgeLabel: edgeLabel,
    edgeWidth: edgeWidth,
    BLOCK_W: BLOCK_W,
    BLOCK_H: BLOCK_H,
    ENVIRONMENT: ENV,
  };
})();
