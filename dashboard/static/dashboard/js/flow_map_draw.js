'use strict';

// Dessin SVG de la carte des flux (spec 2026-10-22 §4). Aucun fetch, aucun
// état global : l'état de la page vit dans flow_map.js, qui rappelle render().
//
//   FlowMapDraw.render(svg, model, state) -> {nodes, edges, bounds}
//     model  : réponse de build_flow_map (blocks, groups, flows, company, start, end…)
//     state  : {expanded: Set<groupKey>, hidden: Set<blockKey>,
//               hiddenKinds: Set<FlowKind> (natures masquées par la légende ; le
//               rangement des blocs n'en dépend pas, les blocs restent affichés),
//               positions: Map<key, {x, y}>, selectedEdge: string|null,
//               editable: bool (« + » des blocs, flèches activables au clavier),
//               trace: {key, port}|null (tracé d'un flux en cours depuis ce bloc)}
//     nodes  : blocs dessinés [{key, type, name, owned, column, x, y, …}]
//     edges  : courbes dessinées, natures masquées exclues (aggregateEdges + width,
//              label, et la géométrie :
//              p0, p3 (pointe), d (chemin), lane (voie d'une courbe du bandeau))
//     bounds : rectangle englobant {x, y, width, height}, pour cadrer la vue
//   FlowMapDraw.aggregateEdges(flows, model, state)
//     -> [{key, from, to, kind, flows: [flow], total}]
//   FlowMapDraw.edgeLabel(edge, end) -> « Soja +2 », « Soja · 2021 » : l'année est
//     ajoutée quand tous les flux de la courbe ont la même année, différente de `end`
//   FlowMapDraw.curve(p0, p3, vertical) -> chemin « M… C… » (Bézier en S)
//
// Dans le SVG : chaque bloc est un <g class="fm-block" data-key>, chaque courbe
// un <g class="fm-edge" data-key>, les bandeaux des <g class="fm-band"
// data-key="environment|market"> (milieu en haut, marché global en bas), le cadre
// d'un groupe déplié un <g class="fm-frame">.
// Si state.editable, les « + » d'un bloc sont des <g class="fm-port"
// data-port="out|in|env|market"> (droite : sortant, gauche : entrant, haut :
// milieu, bas : marché global).
window.FlowMapDraw = (function () {
  var NS = 'http://www.w3.org/2000/svg';
  var ENV = 'environment';
  var MARKET = 'market';

  var BLOCK_W = 170;
  var BLOCK_H = 64;
  var COL_GAP = 120;          // espace horizontal entre deux colonnes
  var ROW_GAP = 36;           // espace vertical entre deux blocs
  var PAD = 40;
  var BAND_Y = 0;
  var BAND_H = 58;
  var BAND_BOTTOM = BAND_Y + BAND_H;
  var BAND_GAP = 80;          // espace entre un bandeau et les blocs
  var TOP = BAND_BOTTOM + BAND_GAP;   // première rangée de blocs, sous le bandeau
  var FRAME_HEAD = 30;        // place du titre d'un groupe déplié
  var FRAME_PAD = 12;
  // Courbes vers / depuis le bandeau : descente dans la gouttière entre deux
  // colonnes, puis virage dans l'espace libre au-dessus du bloc.
  var LANE_BASE = FRAME_PAD + 8;    // première voie, hors du cadre d'un groupe déplié
  var LANE_GAP = 4;
  var LANE_MAX = COL_GAP / 2 - 2;   // une moitié de gouttière par côté
  var TURN = ROW_GAP - 4;           // hauteur du virage au-dessus du bloc
  var LABEL_CHAR_W = 6.2;           // largeur moyenne d'un caractère d'étiquette
  var MIN_WIDTH = 1.5;
  var MAX_WIDTH = 12;
  var NAME_MAX = 20;
  var PILL_TEXT_X = 26;       // retrait du texte d'une entreprise (bloc en pilule)
  var PILL_NAME_MAX = 18;
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

  // Bandeau touché par une courbe : ENV, MARKET ou null (courbe entre deux blocs).
  function bandOf(edge) {
    if (edge.from === ENV || edge.to === ENV) return ENV;
    if (edge.from === MARKET || edge.to === MARKET) return MARKET;
    return null;
  }

  function isBand(key) {
    return key === ENV || key === MARKET;
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
      if (key === ENV || key === MARKET) return key;
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

  // « Soja +2 » : commodité de plus forte quantité et nombre des autres ; suivie
  // de l'année si tous les flux sont d'une même année antérieure à la fin de la plage.
  function edgeLabel(edge, end) {
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
    var label = sorted.length === 1 ? name : interpolate(gettext('%(name)s +%(count)s'),
      { name: name, count: sorted.length - 1 }, true);
    var year = edge.flows[0].year;
    var same = edge.flows.every(function (flow) { return flow.year === year; });
    if (!same || end === undefined || end === null || year === end) return label;
    return interpolate(gettext('%(label)s · %(year)s'), { label: label, year: String(year) },
      true);
  }

  // Épaisseur bornée, proportionnelle à la quantité totale dans la vue.
  function edgeWidth(total, max) {
    if (!max) return MIN_WIDTH;
    return MIN_WIDTH + (MAX_WIDTH - MIN_WIDTH) * (total / max);
  }

  // ── Nœuds visibles ───────────────────────────────────────────────────────
  function visibleNodes(model, state, idx) {
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
      if (bandOf(e)) return;
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

  // Haut du bandeau du marché global : sous le bloc le plus bas, même déplacé.
  function marketTop(nodes) {
    var bottom = nodes.reduce(function (m, n) { return Math.max(m, n.y + BLOCK_H); },
      TOP + BLOCK_H);
    return bottom + BAND_GAP;
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

  function stackOf(node) {
    return node.type === 'group' ? 8 : 0;   // pile de cartes : décalage haut-droite
  }

  // Points d'attache sur les blocs. Courbe horizontale : p0 (bord droit de
  // l'origine) et p3 (bord gauche de la destination). Courbe d'un bandeau : `port`
  // sur le haut du bloc pour le milieu, sur le bas pour le marché global ; ce qui
  // vient du bandeau à gauche, ce qui y va à droite.
  function anchorEdges(edges, byKey) {
    var sides = new Map();   // nodeKey -> {out, in, envIn, envOut, marketIn, marketOut}
    function side(key) {
      if (!sides.has(key)) {
        sides.set(key, { out: [], in: [], envIn: [], envOut: [], marketIn: [], marketOut: [] });
      }
      return sides.get(key);
    }
    function centerY(key) { return byKey.get(key).y + BLOCK_H / 2; }
    edges.forEach(function (e) {
      e.band = bandOf(e);
      e.vertical = e.band !== null;
      if (e.from === ENV) side(e.to).envIn.push(e);
      else if (e.to === ENV) side(e.from).envOut.push(e);
      else if (e.from === MARKET) side(e.to).marketIn.push(e);
      else if (e.to === MARKET) side(e.from).marketOut.push(e);
      else { side(e.from).out.push(e); side(e.to).in.push(e); }
    });
    function attach(list, node, x0, x1, y) {
      slots(x0, x1, list.length).forEach(function (x, i) {
        list[i].port = [x, y];
        list[i].node = node;
      });
    }
    sides.forEach(function (s, key) {
      var node = byKey.get(key);
      var stack = stackOf(node);
      var top = node.y - stack;
      var bottom = node.y + BLOCK_H;
      s.out.sort(function (a, b) { return centerY(a.to) - centerY(b.to); });
      s.in.sort(function (a, b) { return centerY(a.from) - centerY(b.from); });
      slots(node.y + 8, node.y + BLOCK_H - 8, s.out.length).forEach(function (y, i) {
        s.out[i].p0 = [node.x + BLOCK_W + stack, y];
      });
      slots(node.y + 8, node.y + BLOCK_H - 8, s.in.length).forEach(function (y, i) {
        s.in[i].p3 = [node.x, y];
      });
      var left = [node.x + 12, node.x + BLOCK_W / 2 - 6];
      var right = [node.x + BLOCK_W / 2 + 6, node.x + BLOCK_W - 12];
      attach(s.envIn, node, left[0], left[1], top);
      attach(s.envOut, node, right[0], right[1], top);
      attach(s.marketIn, node, left[0], left[1], bottom);
      attach(s.marketOut, node, right[0], right[1], bottom);
    });
  }

  function arrowLength(width) { return 5 + width * 0.9; }

  // Courbe horizontale : S lisse du bord droit de l'origine au bord gauche de la
  // destination, flèche au bout.
  function routeHorizontal(e) {
    var base = [e.p3[0] - arrowLength(e.width), e.p3[1]];
    e.dir = [1, 0];
    e.base = base;
    e.d = curve(e.p0, base, false);
    var mid = midpoint(e.p0, base, false);
    e.labelAt = [mid[0], mid[1] - e.width / 2 - 5];
    e.labelAnchor = 'middle';
  }

  // Voies de la gouttière : une par courbe d'un bandeau, réparties en s'éloignant
  // du bloc. Gouttière gauche : ce qui vient d'un bandeau ; droite : ce qui y va.
  // Voie la plus proche pour la rangée la plus proche du bandeau ; à rangée égale,
  // l'ordre des attaches est conservé pour que les courbes ne se croisent pas.
  // Les voies du milieu passent au plus près, celles du marché au-delà, pour que
  // les deux familles ne se superposent pas. Trop de voies : on resserre pour
  // rester dans la demi-gouttière.
  function sortLanes(list, left, fromBelow) {
    return list.sort(function (a, b) {
      var dy = fromBelow ? b.port[1] - a.port[1] : a.port[1] - b.port[1];
      if (dy) return dy;
      return left ? b.port[0] - a.port[0] : a.port[0] - b.port[0];
    });
  }

  function assignLanes(list, left) {
    var env = sortLanes(list.filter(function (e) { return e.band === ENV; }), left, false);
    var market = sortLanes(list.filter(function (e) { return e.band === MARKET; }), left, true);
    env.forEach(function (e, i) { e.laneIndex = i; });
    market.forEach(function (e, i) { e.laneIndex = i; });
    list = env.concat(market);
    var offsets = [];
    var d = LANE_BASE;
    list.forEach(function (e, i) {
      d += (i ? list[i - 1].width / 2 + LANE_GAP : 0) + e.width / 2;
      offsets.push(d);
    });
    var last = list[list.length - 1];
    var reach = offsets[offsets.length - 1] + last.width / 2;
    var squeeze = reach > LANE_MAX ? (LANE_MAX - LANE_BASE) / (reach - LANE_BASE) : 1;
    list.forEach(function (e, i) {
      var offset = LANE_BASE + (offsets[i] - LANE_BASE) * squeeze;
      var node = e.node;
      // offset ≥ LANE_BASE dépasse la pile de cartes d'un groupe (8).
      e.lane = left ? node.x - offset : node.x + BLOCK_W + offset;
    });
  }

  // Courbe du milieu : descente verticale dans la gouttière, puis virage en S
  // dans l'espace libre au-dessus du bloc. Le haut d'un bloc trop proche du
  // bandeau (bloc déplacé) reçoit une simple courbe en S.
  function routeEnvironment(e) {
    var down = e.from === ENV;
    var len = arrowLength(e.width);
    var top = e.port[1];
    var turn = top - TURN;
    var direct = turn < BAND_BOTTOM + 8;
    var lane = e.lane;
    var h;
    if (down) {
      e.p0 = [lane, BAND_BOTTOM];
      e.p3 = e.port;
      e.dir = [0, 1];
      e.base = [e.port[0], top - len];
      h = (e.base[1] - turn) / 2;
      e.d = direct ? curve(e.p0, e.base, true)
        : 'M' + pt(e.p0) + ' L' + pt([lane, turn]) + ' C' + pt([lane, turn + h]) + ' '
          + pt([e.base[0], e.base[1] - h]) + ' ' + pt(e.base);
    } else {
      e.p0 = e.port;
      e.p3 = [lane, BAND_BOTTOM];
      e.dir = [0, -1];
      e.base = [lane, BAND_BOTTOM + len];
      h = (top - turn) / 2;
      e.d = direct ? curve(e.p0, e.base, true)
        : 'M' + pt(e.p0) + ' C' + pt([e.port[0], top - h]) + ' ' + pt([lane, turn + h]) + ' '
          + pt([lane, turn]) + ' L' + pt(e.base);
    }
    // Étiquette le long de la voie, sous le bandeau, décalée d'une voie à l'autre,
    // écrite du côté opposé au bloc.
    var y = Math.min(BAND_BOTTOM + 30 + 13 * e.laneIndex, Math.max(turn - 2, BAND_BOTTOM + 30));
    var gap = e.width / 2 + 4;
    e.labelAt = down ? [lane - gap, y] : [lane + gap, y];
    e.labelAnchor = down ? 'end' : 'start';
  }

  // Courbe du marché global : miroir de celle du milieu, par le bas du bloc,
  // jusqu'au haut du bandeau du marché (ordonnée `market`).
  function routeMarket(e, market) {
    var up = e.from === MARKET;
    var len = arrowLength(e.width);
    var bottom = e.port[1];
    var turn = bottom + TURN;
    var direct = turn > market - 8;
    var lane = e.lane;
    var h;
    if (up) {
      e.p0 = [lane, market];
      e.p3 = e.port;
      e.dir = [0, -1];
      e.base = [e.port[0], bottom + len];
      h = (turn - e.base[1]) / 2;
      e.d = direct ? curve(e.p0, e.base, true)
        : 'M' + pt(e.p0) + ' L' + pt([lane, turn]) + ' C' + pt([lane, turn - h]) + ' '
          + pt([e.base[0], e.base[1] + h]) + ' ' + pt(e.base);
    } else {
      e.p0 = e.port;
      e.p3 = [lane, market];
      e.dir = [0, 1];
      e.base = [lane, market - len];
      h = (turn - bottom) / 2;
      e.d = direct ? curve(e.p0, e.base, true)
        : 'M' + pt(e.p0) + ' C' + pt([e.port[0], bottom + h]) + ' ' + pt([lane, turn - h])
          + ' ' + pt([lane, turn]) + ' L' + pt(e.base);
    }
    // Étiquette le long de la voie, au-dessus du bandeau, décalée d'une voie à
    // l'autre, écrite du côté opposé au bloc.
    var y = Math.max(market - 24 - 13 * e.laneIndex, Math.min(turn + 10, market - 24));
    var gap = e.width / 2 + 4;
    e.labelAt = up ? [lane - gap, y] : [lane + gap, y];
    e.labelAnchor = up ? 'end' : 'start';
  }

  function routeEdges(edges, market) {
    var gutters = new Map();   // côté + bord de colonne -> courbes des bandeaux
    edges.forEach(function (e) {
      if (!e.vertical) { routeHorizontal(e); return; }
      var left = isBand(e.from);
      var key = (left ? 'L' : 'R') + Math.round(e.node.x);
      if (!gutters.has(key)) gutters.set(key, { left: left, edges: [] });
      gutters.get(key).edges.push(e);
    });
    gutters.forEach(function (g) {
      assignLanes(g.edges, g.left);
      g.edges.forEach(function (e) {
        if (e.band === ENV) routeEnvironment(e);
        else routeMarket(e, market);
      });
    });
  }

  // ── Dessin ───────────────────────────────────────────────────────────────
  function flowLine(flow, edge, idx) {
    var line = flow.what.name + ' · ' + quantity(flow.quantity) + ' ' + flow.what.unit
      + ' · ' + flow.year;
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

  function drawEdge(layer, edge, selected, title, editable) {
    var w = edge.width;
    var half = 3.5 + w * 0.75;
    var base = edge.base;
    var perp = [-edge.dir[1], edge.dir[0]];

    var g = el('g', {
      class: 'fm-edge fm-edge--' + kindClass(edge.kind) + (selected ? ' is-selected' : ''),
      'data-key': edge.key,
    }, layer);
    if (editable) {
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      g.setAttribute('aria-label', interpolate(gettext('Modifier : %(title)s'),
        { title: title.split('\n')[0] }, true));
    }
    text('title', {}, title, g);
    el('path', { class: 'fm-edge__hit', d: edge.d, 'stroke-width': w + 12 }, g);
    el('path', { class: 'fm-edge__line', d: edge.d, 'stroke-width': w }, g);
    el('path', {
      class: 'fm-edge__arrow',
      d: 'M' + pt(edge.p3) + ' L' + pt([base[0] + perp[0] * half, base[1] + perp[1] * half])
        + ' L' + pt([base[0] - perp[0] * half, base[1] - perp[1] * half]) + ' Z',
    }, g);
    text('text', {
      class: 'fm-edge__label', x: Math.round(edge.labelAt[0]), y: Math.round(edge.labelAt[1]),
      'text-anchor': edge.labelAnchor,
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

  // « + » d'un bloc : pas sur un groupe replié ; ceux du haut (milieu) et du bas
  // (marché global) seulement sur un actif ou une entreprise.
  var PORTS = [
    { port: 'in', x: 0, y: BLOCK_H / 2 },
    { port: 'out', x: BLOCK_W, y: BLOCK_H / 2 },
    { port: 'env', x: BLOCK_W / 2, y: 0 },
    { port: 'market', x: BLOCK_W / 2, y: BLOCK_H },
  ];

  function portLabel(port) {
    if (port === 'in') return gettext('Ajouter un flux entrant vers %(name)s');
    if (port === 'out') return gettext('Ajouter un flux sortant de %(name)s');
    if (port === 'market') return gettext('Ajouter un flux avec le marché global pour %(name)s');
    return gettext('Ajouter un flux avec le milieu pour %(name)s');
  }

  function drawPorts(g, node) {
    if (node.type === 'group') return;
    PORTS.forEach(function (p) {
      var banded = p.port === 'env' || p.port === 'market';
      if (banded && node.type !== 'asset' && node.type !== 'company') return;
      var label = interpolate(portLabel(p.port), { name: node.name }, true);
      var port = el('g', {
        class: 'fm-port fm-port--' + p.port, 'data-port': p.port, tabindex: '0',
        role: 'button', 'aria-label': label,
      }, g);
      text('title', {}, label, port);
      el('circle', { cx: p.x, cy: p.y, r: 9 }, port);
      text('text', { x: p.x, y: p.y + 4, 'text-anchor': 'middle' }, '+', port);
    });
  }

  function drawBlock(layer, node, focusKey, state) {
    var classes = ['fm-block', 'fm-block--' + node.type];
    if (node.owned) classes.push('is-owned');
    if (node.key === focusKey) classes.push('is-focus');
    if (state.trace && state.trace.key === node.key) classes.push('is-trace-source');
    var g = el('g', {
      class: classes.join(' '), 'data-key': node.key,
      transform: 'translate(' + pt([node.x, node.y]) + ')',
    }, layer);
    var type = typeLabel(node);
    text('title', {}, type ? type + ' — ' + node.name : node.name, g);
    if (state.trace && node.type !== 'group') {
      // Tracé en cours : chaque bloc se choisit au clavier comme autre extrémité.
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
    }
    if (node.type === 'group') {
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      g.setAttribute('aria-expanded', 'false');
      [8, 4].forEach(function (offset) {
        el('rect', { class: 'fm-block__stack', x: offset, y: -offset, width: BLOCK_W,
          height: BLOCK_H, rx: 8 }, g);
      });
    }
    // Une entreprise est une pilule (bouts en demi-cercle), un actif ou un lieu
    // un rectangle : le texte s'écarte des bouts arrondis.
    var pill = node.type === 'company';
    var textX = pill ? PILL_TEXT_X : 12;
    el('rect', { class: 'fm-block__card', width: BLOCK_W, height: BLOCK_H,
      rx: pill ? BLOCK_H / 2 : 8 }, g);
    if (type) {
      text('text', { class: 'fm-block__type', x: textX, y: 22 }, type.toLocaleUpperCase(), g);
    }
    text('text', { class: 'fm-block__name', x: textX, y: type ? 46 : 38 },
      truncate(node.name, pill ? PILL_NAME_MAX : NAME_MAX), g);
    if (node.type === 'group') {
      text('text', { class: 'fm-block__toggle', x: 12, y: BLOCK_H - 4 },
        '▸ ' + gettext('déplier'), g);
    }
    if (node.key !== focusKey) {
      var menu = el('g', {
        class: 'fm-block__menu', 'data-action': 'menu', tabindex: '0', role: 'button',
        'aria-label': interpolate(gettext('Actions du bloc %(name)s'), { name: node.name }, true),
      }, g);
      var menuX = pill ? BLOCK_W - 26 : BLOCK_W - 16;
      el('circle', { cx: menuX, cy: 17, r: 10 }, menu);
      text('text', { x: menuX, y: 21, 'text-anchor': 'middle' }, '⋯', menu);
    }
    if (state.editable) drawPorts(g, node);
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

  function drawBand(layer, bounds, key, y, label) {
    var g = el('g', { class: 'fm-band fm-band--' + key, 'data-key': key }, layer);
    el('rect', { class: 'fm-band__rect', x: bounds.x, y: y, width: bounds.width,
      height: BAND_H, rx: 10 }, g);
    text('text', { class: 'fm-band__label', x: bounds.x + 16, y: y + 34 }, label, g);
  }

  function computeBounds(nodes, frames, edges, market) {
    var minX = PAD;
    var maxX = PAD + BLOCK_W;
    var maxY = TOP + BLOCK_H;
    nodes.forEach(function (n) {
      minX = Math.min(minX, n.x);
      maxX = Math.max(maxX, n.x + BLOCK_W + 8);   // + 8 : pile de cartes d'un groupe
      maxY = Math.max(maxY, n.y + BLOCK_H);
    });
    edges.forEach(function (e) {
      if (!e.vertical) return;
      var labelW = e.label.length * LABEL_CHAR_W;
      if (e.labelAnchor === 'end') minX = Math.min(minX, e.labelAt[0] - labelW);
      else maxX = Math.max(maxX, e.labelAt[0] + labelW);
    });
    frames.forEach(function (b) {
      minX = Math.min(minX, b.x);
      maxX = Math.max(maxX, b.x + b.width);
      maxY = Math.max(maxY, b.y + b.height);
    });
    maxY = Math.max(maxY, market + BAND_H);
    var x = minX - PAD;
    var y = BAND_Y - PAD / 2;
    return { x: x, y: y, width: maxX + PAD - x, height: maxY + PAD / 2 - y };
  }

  // Les natures masquées (légende) n'interviennent qu'au dessin : rangement des
  // blocs et échelle des épaisseurs restent ceux de la carte complète, pour que
  // masquer une nature ne déplace rien.
  function render(svg, model, state) {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var idx = indexModel(model);
    var hiddenKinds = state.hiddenKinds || new Set();
    var edges = aggregateEdges(model.flows, model, state);
    var nodes = visibleNodes(model, state, idx);
    var byKey = new Map(nodes.map(function (n) { return [n.key, n]; }));
    edges = edges.filter(function (e) {
      return (isBand(e.from) || byKey.has(e.from)) && (isBand(e.to) || byKey.has(e.to));
    });
    placeNodes(nodes, edges, state);
    var market = marketTop(nodes);
    var max = edges.reduce(function (m, e) { return Math.max(m, e.total); }, 0);
    edges = edges.filter(function (e) { return !hiddenKinds.has(e.kind); });
    edges.forEach(function (e) {
      e.width = edgeWidth(e.total, max);
      e.label = edgeLabel(e, model.end);
    });
    anchorEdges(edges, byKey);
    routeEdges(edges, market);

    function name(key) {
      if (key === ENV) return gettext('Environnement');
      if (key === MARKET) return gettext('Marché global');
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
    var bounds = computeBounds(nodes, frames, edges, market);
    drawBand(bandLayer, bounds, ENV, BAND_Y,
      gettext('Environnement — milieu naturel (eau, air, sol)'));
    drawBand(bandLayer, bounds, MARKET, market,
      gettext('Marché global'));

    edges.forEach(function (e) {
      drawEdge(edgeLayer, e, e.key === state.selectedEdge, edgeTitle(e, idx, name),
        !!state.editable);
    });
    var focusKey = 'company:' + model.company.id;
    nodes.forEach(function (n) { drawBlock(blockLayer, n, focusKey, state); });

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
    MARKET: MARKET,
  };
})();
