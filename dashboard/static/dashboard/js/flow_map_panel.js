'use strict';

// Saisie des flux sur la carte (spec 2026-10-22 §5.1, §5.2), Créateurs seulement.
//
//   « + » droite / gauche d'un bloc : mode tracé, puis clic sur l'autre bloc, sur le
//   bandeau Environnement ou sur le fond (extrémité inconnue) ; Échap annule.
//   « + » du haut : fiche directe avec le milieu.
//   Clic sur une flèche : panneau latéral en formulaire modifiable.
//
//   FlowMapPanel.openNewFlow(fromKey, toKey) -> bool   fiche de création (faux :
//                                                      aucune nature permise)
//   FlowMapPanel.openEdge(edge)       panneau d'une flèche (edge de FlowMapDraw.render)
//   FlowMapPanel.close()              ferme sans enregistrer
//   FlowMapPanel.confirm(message, {confirmLabel, danger}) -> Promise<bool>
//                                     fenêtre modale de confirmation (focus piégé,
//                                     retour du focus ; Échap ou clic hors = non)
// Après chaque écriture réussie : événement « flowmap:changed » sur document
// (flow_map.js recharge la carte).
window.FlowMapPanel = (function () {
  var ENV = 'environment';
  var UNKNOWN_IN = 'unknown-in';
  var UNKNOWN_OUT = 'unknown-out';
  var SEARCH_MIN = 2;
  var SEARCH_DELAY = 200;
  var NOTICE_DELAY = 6000;
  var FIELDS = ['kind', 'what', 'quantity', 'year', 'tier', 'scope', 'source', 'reference'];
  var OPTIONAL_FIELDS = ['tier', 'scope', 'source', 'reference'];

  var els = {};
  var urls = {};
  var trace = null;         // {key, port} : tracé en cours
  var sheet = null;         // fiche ouverte {mode: 'new'|'edit', options, option, edge, flow}
  var opener = null;        // sélecteur de l'élément de la carte qui a ouvert la fiche
  var what = null;          // commodité choisie {id, name, unit}
  var options = [];         // options de la liste de commodités
  var activeOption = -1;
  var searchRequest = 0;
  var searchTimer = 0;
  var createName = '';
  var busy = false;
  var noticeTimer = 0;
  var pendingConfirm = null;
  var refocus = false;      // rendre le focus à l'ouvreur après le rechargement

  // ── Utilitaires ──────────────────────────────────────────────────────────
  function getCookie(name) {
    var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
  }

  function post(url, payload) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify(payload),
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        return { ok: response.ok, status: response.status, data: data || {} };
      });
    });
  }

  function idUrl(template, id) {
    return template.replace('/0/', '/' + id + '/');
  }

  function attr(value) {
    return window.CSS && CSS.escape ? CSS.escape(value) : value;
  }

  function changed() {
    document.dispatchEvent(new CustomEvent('flowmap:changed'));
  }

  function quantityText(value, grouping) {
    return Number(value).toLocaleString(APP_LOCALE, {
      maximumFractionDigits: grouping ? 2 : 10, useGrouping: grouping,
    });
  }

  // Type d'extrémité d'une clé de bloc, au sens de FLOW_RULES.
  function typeOf(key) {
    if (key === ENV) return 'environment';
    if (key === UNKNOWN_IN || key === UNKNOWN_OUT) return null;
    return key.split(':')[0];
  }

  function blockName(key) {
    if (key === ENV) return gettext('Environnement');
    var model = FlowMap.model();
    var found = model && (model.blocks.concat(model.groups || [])).find(function (b) {
      return b.key === key;
    });
    if (found) return found.name;
    if (key === UNKNOWN_IN) return gettext('Origine inconnue');
    if (key === UNKNOWN_OUT) return gettext('Destination inconnue');
    return key;
  }

  function kindLabel(kind) {
    var found = FlowMap.kinds.find(function (k) { return k.value === kind; });
    return found ? found.label : kind;
  }

  function allowed(kind, fromKey, toKey) {
    var rule = FlowMap.rules[kind];
    return !!rule && rule.origins.indexOf(typeOf(fromKey)) >= 0
      && rule.destinations.indexOf(typeOf(toKey)) >= 0;
  }

  // Natures permises entre deux blocs. Avec le milieu, le sens découle de la
  // nature : les deux sens sont proposés (consommation milieu → bloc, émission
  // et déchet bloc → milieu), celui du tracé d'abord.
  function optionsFor(a, b, bothWays) {
    var list = [];
    FlowMap.kinds.forEach(function (k) {
      if (allowed(k.value, a, b)) list.push({ kind: k.value, from: a, to: b });
    });
    if (bothWays && (a === ENV) !== (b === ENV)) {
      FlowMap.kinds.forEach(function (k) {
        var taken = list.some(function (o) { return o.kind === k.value; });
        if (!taken && allowed(k.value, b, a)) list.push({ kind: k.value, from: b, to: a });
      });
    }
    return list;
  }

  function routeText(fromKey, toKey) {
    return interpolate(gettext('%(from)s → %(to)s'),
      { from: blockName(fromKey), to: blockName(toKey) }, true);
  }

  function findEdge(key) {
    var last = FlowMap.lastRender();
    return last ? last.edges.find(function (e) { return e.key === key; }) : null;
  }

  // ── Messages ─────────────────────────────────────────────────────────────
  function notice(message) {
    clearTimeout(noticeTimer);
    els.notice.textContent = message;
    els.notice.hidden = false;
    noticeTimer = setTimeout(function () { els.notice.hidden = true; }, NOTICE_DELAY);
  }

  function inputFor(field) {
    return document.getElementById('fm-' + field);
  }

  function clearErrors() {
    FIELDS.concat(['__all__']).forEach(function (field) {
      var p = document.getElementById('fm-error-' + field);
      p.textContent = '';
      p.hidden = true;
      var input = inputFor(field);
      if (input) input.removeAttribute('aria-invalid');
    });
  }

  // {champ: [messages]} : les champs inconnus de la fiche (extrémités…) vont
  // dans le message général.
  function showErrors(errors) {
    var focus = null;
    Object.keys(errors).forEach(function (field) {
      var target = FIELDS.indexOf(field) >= 0 ? field : '__all__';
      var p = document.getElementById('fm-error-' + target);
      var text = [].concat(errors[field]).join(' ');
      p.textContent = p.textContent ? p.textContent + ' ' + text : text;
      p.hidden = false;
      var input = inputFor(target);
      if (input) {
        input.setAttribute('aria-invalid', 'true');
        if (!focus) focus = input;
      }
      if (OPTIONAL_FIELDS.indexOf(target) >= 0) els.more.open = true;
    });
    if (focus) focus.focus();
    else if (!els.errorAll.hidden) els.errorAll.focus();
  }

  function unexpected(err) {
    console.error('flow_map write failed:', err);
    showErrors({ __all__: [gettext('Le serveur est injoignable. Réessayez.')] });
  }

  function setBusy(on) {
    busy = on;
    els.save.disabled = on;
    els.remove.disabled = on;
    els.panel.setAttribute('aria-busy', on ? 'true' : 'false');
  }

  // ── Tracé d'un flux ──────────────────────────────────────────────────────
  function portSelector(key, port) {
    return '.fm-block[data-key="' + attr(key) + '"] .fm-port[data-port="' + port + '"]';
  }

  function focusOpener() {
    var target = opener && FlowMap.svg.querySelector(opener);
    (target || FlowMap.svg).focus({ preventScroll: true });
  }

  function startTrace(key, port) {
    if (!FlowMap.model()) return;
    close({ focus: false });
    trace = { key: key, port: port };
    opener = portSelector(key, port);
    FlowMap.state.trace = trace;
    FlowMap.svg.classList.add('is-tracing');
    if (port === 'out') {
      els.traceText.textContent = gettext('Cliquez le bloc de destination, le bandeau '
        + 'Environnement, ou le fond pour une destination inconnue. Échap : annuler.');
      els.traceUnknown.textContent = gettext('Destination inconnue');
    } else {
      els.traceText.textContent = gettext('Cliquez le bloc d’origine, le bandeau '
        + 'Environnement, ou le fond pour une origine inconnue. Échap : annuler.');
      els.traceUnknown.textContent = gettext('Origine inconnue');
    }
    els.trace.hidden = false;
    FlowMap.redraw();
    focusOpener();
  }

  function cancelTrace() {
    if (!trace) return;
    trace = null;
    FlowMap.state.trace = null;
    FlowMap.svg.classList.remove('is-tracing');
    els.trace.hidden = true;
    FlowMap.redraw();
  }

  // Autre extrémité choisie : un bloc, le milieu ou null (inconnue).
  function finishTrace(otherKey) {
    var t = trace;
    if (otherKey === null || typeOf(otherKey) === null) {
      otherKey = t.port === 'out' ? UNKNOWN_OUT : UNKNOWN_IN;
    }
    cancelTrace();
    if (t.port === 'out') openNewFlow(t.key, otherKey);
    else openNewFlow(otherKey, t.key);
  }

  function onTap(info) {
    if (!FlowMap.canEdit) return false;
    if (trace) {
      if (info.type === 'port') {
        if (info.port === 'env') { cancelTrace(); openEnvironment(info.key); }
        else startTrace(info.key, info.port);
        return true;
      }
      if (info.type === 'block') {
        if (info.key.indexOf('group:') === 0) {
          // Le groupe se déplie (comportement par défaut) : choisir un de ses actifs.
          notice(gettext('Groupe déplié : choisissez l’un de ses actifs.'));
          return false;
        }
        finishTrace(info.key);
        return true;
      }
      if (info.type === 'band') { finishTrace(ENV); return true; }
      if (info.type === 'background') { finishTrace(null); return true; }
      return true;   // flèches et cadres de groupe ignorés pendant le tracé
    }
    if (info.type === 'port') {
      if (info.port === 'env') openEnvironment(info.key);
      else startTrace(info.key, info.port);
      return true;
    }
    if (info.type === 'edge') {
      var edge = findEdge(info.key);
      if (!edge) return false;
      opener = '.fm-edge[data-key="' + attr(edge.key) + '"]';
      openEdge(edge);
      return true;
    }
    return false;
  }

  function openEnvironment(key) {
    opener = portSelector(key, 'env');
    openNewFlow(ENV, key);
  }

  // ── Fiche ────────────────────────────────────────────────────────────────
  function openNewFlow(fromKey, toKey) {
    cancelTrace();
    if (!FlowMap.model()) return false;   // carte vide (chargement échoué)
    var list = optionsFor(fromKey, toKey, true);
    if (!list.length) {
      notice(interpolate(gettext('Aucune nature de flux n’est possible de « %(from)s » '
        + 'vers « %(to)s ».'), { from: blockName(fromKey), to: blockName(toKey) }, true));
      return false;
    }
    sheet = { mode: 'new', options: list, edge: null, flow: null };
    if (FlowMap.state.selectedEdge !== null) {
      FlowMap.state.selectedEdge = null;
      FlowMap.redraw();
    }
    els.title.textContent = gettext('Nouveau flux');
    els.flowList.textContent = '';
    els.flows.hidden = true;
    els.add.hidden = true;
    els.remove.hidden = true;
    fillForm(null);
    renderKinds(list, list[0].kind);
    showPanel(els.what);
    return true;
  }

  function openEdge(edge) {
    cancelTrace();
    if (!FlowMap.model()) return;
    sheet = { mode: 'edit', edge: edge, flow: null, options: [] };
    FlowMap.state.selectedEdge = edge.key;
    FlowMap.redraw();
    els.title.textContent = gettext('Modifier le flux');
    els.remove.hidden = false;
    var collapsed = edge.from.indexOf('group:') === 0 || edge.to.indexOf('group:') === 0;
    els.add.hidden = collapsed;
    renderFlowList(edge);
    selectFlow(edge.flows[0]);
    var checked = els.flowList.querySelector('input:checked');
    showPanel(edge.flows.length > 1 && checked ? checked : els.quantity);
  }

  function selectFlow(flow) {
    sheet.flow = flow;
    var list = optionsFor(flow.from, flow.to, false);
    if (!list.some(function (o) { return o.kind === flow.kind; })) {
      list.unshift({ kind: flow.kind, from: flow.from, to: flow.to });
    }
    sheet.options = list;
    fillForm(flow);
    renderKinds(list, flow.kind);
  }

  // Membre d'un groupe replié porteur du flux (affiché dans la liste).
  function memberOf(flow, edge) {
    if (edge.from !== flow.from) return blockName(flow.from);
    if (edge.to !== flow.to) return blockName(flow.to);
    return '';
  }

  function renderFlowList(edge) {
    els.flowList.textContent = '';
    els.flows.hidden = edge.flows.length < 2;
    if (edge.flows.length < 2) return;
    edge.flows.forEach(function (flow, i) {
      var label = document.createElement('label');
      label.className = 'fm-panel__flow';
      var input = document.createElement('input');
      input.type = 'radio';
      input.name = 'fm-flow';
      input.value = String(flow.id);
      input.checked = i === 0;
      input.addEventListener('change', function () {
        if (input.checked) selectFlow(flow);
      });
      var text = document.createElement('span');
      text.textContent = flow.what.name + ' · ' + quantityText(flow.quantity, true) + ' '
        + flow.what.unit;
      label.appendChild(input);
      label.appendChild(text);
      var member = memberOf(flow, edge);
      if (member) {
        var small = document.createElement('span');
        small.className = 'fm-panel__flow-member';
        small.textContent = member;
        label.appendChild(small);
      }
      els.flowList.appendChild(label);
    });
  }

  function renderKinds(list, selected) {
    els.kinds.textContent = '';
    list.forEach(function (option) {
      var label = document.createElement('label');
      label.className = 'fm-chip fm-chip--' + option.kind.toLowerCase();
      var input = document.createElement('input');
      input.type = 'radio';
      input.name = 'fm-kind';
      input.value = option.kind;
      input.checked = option.kind === selected;
      input.addEventListener('change', function () {
        if (input.checked) selectKind(option);
      });
      var swatch = document.createElement('i');
      swatch.className = 'fm-chip__swatch';
      swatch.setAttribute('aria-hidden', 'true');
      var text = document.createElement('span');
      text.textContent = kindLabel(option.kind);
      label.appendChild(input);
      label.appendChild(swatch);
      label.appendChild(text);
      els.kinds.appendChild(label);
    });
    selectKind(list.find(function (o) { return o.kind === selected; }) || list[0]);
  }

  function selectKind(option) {
    sheet.option = option;
    els.route.textContent = routeText(option.from, option.to);
    els.scopeField.hidden = option.kind !== 'EMISSION';
  }

  function fillForm(flow) {
    clearErrors();
    hideList();
    hideCreate();
    setWhat(flow ? flow.what : null);
    els.what.value = flow ? flow.what.name : '';
    els.quantity.value = flow ? quantityText(flow.quantity, false) : '';
    els.year.value = String(flow ? flow.year : FlowMap.model().year);
    els.tier.value = String(flow ? flow.tier : 0);
    els.scope.value = flow ? flow.scope : 'undefined';
    els.source.value = flow ? flow.source : '';
    els.reference.value = flow ? flow.reference : '';
    els.more.open = !!flow && (flow.tier > 0 || flow.scope !== 'undefined' || !!flow.source
      || !!flow.reference);
  }

  function showPanel(focusTarget) {
    setBusy(false);
    els.panel.hidden = false;
    els.panel.scrollTop = 0;
    (focusTarget || els.panel).focus();
  }

  function close(opts) {
    if (els.panel.hidden) return;
    var hadFocus = focusInPanel();
    els.panel.hidden = true;
    hideList();
    hideCreate();
    sheet = null;
    if (FlowMap.state.selectedEdge !== null) {
      var mapFocus = mapSelector(document.activeElement);
      FlowMap.state.selectedEdge = null;
      FlowMap.redraw();
      // Le redessin remplace l'élément de la carte qui avait le focus.
      var again = mapFocus && FlowMap.svg.querySelector(mapFocus);
      if (again) again.focus({ preventScroll: true });
    }
    if (hadFocus && !(opts && opts.focus === false)) focusOpener();
  }

  // Sélecteur stable d'un élément focalisable de la carte (survit au redessin).
  function mapSelector(node) {
    if (!node || !FlowMap.svg.contains(node) || node === FlowMap.svg) return null;
    var block = node.closest('.fm-block');
    if (node.classList.contains('fm-port') && block) {
      return portSelector(block.dataset.key, node.dataset.port);
    }
    var kinds = ['fm-block', 'fm-edge', 'fm-frame'];
    for (var i = 0; i < kinds.length; i++) {
      if (node.classList.contains(kinds[i]) && node.dataset.key) {
        return '.' + kinds[i] + '[data-key="' + attr(node.dataset.key) + '"]';
      }
    }
    return null;
  }

  // Focus dans le panneau, ou perdu parce que le bouton focalisé a été désactivé
  // pendant l'écriture (Supprimer, Enregistrer).
  function focusInPanel() {
    var active = document.activeElement;
    return !active || active === document.body || els.panel.contains(active);
  }

  // Écriture réussie : on ferme, on prévient, la carte se recharge.
  // Le rechargement redessine la carte et retire l'élément focalisé : le focus
  // revient à l'ouvreur (ou à la carte) une fois la carte rechargée.
  function done(message) {
    var hadFocus = focusInPanel();
    close();
    notice(message);
    refocus = hadFocus;
    changed();
  }

  function gone(data) {
    var errors = (data && data.errors && data.errors.__all__) || [];
    var hadFocus = focusInPanel();
    close();
    notice(errors[0] || gettext('Ce flux n’existe plus.'));
    refocus = hadFocus;
    changed();
  }

  function answer(res, message) {
    if (res.ok) done(message);
    else if (res.status === 404) gone(res.data);
    else showErrors(res.data.errors || { __all__: [gettext('Erreur inattendue du serveur.')] });
  }

  function save(event) {
    event.preventDefault();
    if (busy || !sheet) return;
    clearErrors();
    if (!what) {
      showErrors({ what: [gettext('Choisissez une commodité dans la liste, ou créez-la.')] });
      return;
    }
    var option = sheet.option;
    var payload = {
      kind: option.kind,
      what_id: what.id,
      quantity: els.quantity.value.trim(),
      year: els.year.value.trim(),
      tier: parseInt(els.tier.value, 10) || 0,
      source: els.source.value.trim(),
      reference: els.reference.value.trim(),
    };
    if (option.kind === 'EMISSION') payload.scope = els.scope.value;
    var creating = sheet.mode === 'new';
    var url;
    if (creating) {
      payload.from = option.from;
      payload.to = option.to;
      url = urls.flowCreate;
    } else {
      url = idUrl(urls.flowUpdate, sheet.flow.id);
    }
    setBusy(true);
    post(url, payload)
      .then(function (res) {
        answer(res, creating ? gettext('Flux créé.') : gettext('Flux enregistré.'));
      })
      .catch(unexpected)
      .finally(function () { setBusy(false); });
  }

  function remove() {
    if (busy || !sheet || !sheet.flow) return;
    var flow = sheet.flow;
    var message = interpolate(gettext('Supprimer le flux « %(what)s » (%(quantity)s %(unit)s, '
      + '%(year)s) ? Cette suppression est définitive.'), {
      what: flow.what.name, quantity: quantityText(flow.quantity, true),
      unit: flow.what.unit, year: flow.year,
    }, true);
    confirm(message, { confirmLabel: gettext('Supprimer') }).then(function (ok) {
      if (!ok || !sheet || sheet.flow !== flow) return;
      clearErrors();
      setBusy(true);
      post(idUrl(urls.flowDelete, flow.id), {})
        .then(function (res) { answer(res, gettext('Flux supprimé.')); })
        .catch(unexpected)
        .finally(function () { setBusy(false); });
    });
  }

  // ── Commodité : recherche et création ────────────────────────────────────
  function setWhat(item) {
    what = item ? { id: item.id, name: item.name, unit: item.unit } : null;
    els.unit.textContent = what && what.unit ? what.unit : '—';
  }

  function onWhatInput() {
    if (what && els.what.value !== what.name) setWhat(null);
    hideCreate();
    clearTimeout(searchTimer);
    var q = els.what.value.trim();
    if (q.length < SEARCH_MIN) {
      searchRequest += 1;
      hideList();
      return;
    }
    searchTimer = setTimeout(function () { search(q); }, SEARCH_DELAY);
  }

  function search(q) {
    var mine = ++searchRequest;
    fetch(urls.search + '?type=commodity&q=' + encodeURIComponent(q), {
      headers: { Accept: 'application/json' },
    })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (mine === searchRequest && document.activeElement === els.what) {
          renderList(q, data.results || []);
        }
      })
      .catch(function (err) {
        if (mine !== searchRequest) return;
        console.error('commodity search failed:', err);
        renderList(q, []);
      });
  }

  function renderList(q, results) {
    options = results.map(function (r) {
      return {
        item: { id: r.id, name: r.name, unit: r.detail },
        label: r.detail ? r.name + ' — ' + r.detail : r.name,
      };
    });
    var exact = results.some(function (r) { return r.name.toLowerCase() === q.toLowerCase(); });
    if (!exact) {
      options.push({
        create: q, label: interpolate(gettext('+ Créer « %(name)s »…'), { name: q }, true),
      });
    }
    els.list.textContent = '';
    options.forEach(function (option, i) {
      var li = document.createElement('li');
      li.id = 'fm-what-option-' + i;
      li.className = 'fm-combo__option' + (option.create ? ' fm-combo__option--create' : '');
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', 'false');
      li.textContent = option.label;
      li.addEventListener('click', function () { choose(i); });
      els.list.appendChild(li);
    });
    activeOption = -1;
    els.what.removeAttribute('aria-activedescendant');
    els.list.hidden = false;
    els.what.setAttribute('aria-expanded', 'true');
  }

  function hideList() {
    if (!els.list) return;
    els.list.hidden = true;
    els.what.setAttribute('aria-expanded', 'false');
    els.what.removeAttribute('aria-activedescendant');
    activeOption = -1;
  }

  function setActive(index) {
    var items = els.list.children;
    if (!items.length) return;
    activeOption = (index + items.length) % items.length;
    Array.prototype.forEach.call(items, function (li, i) {
      li.classList.toggle('is-active', i === activeOption);
      li.setAttribute('aria-selected', i === activeOption ? 'true' : 'false');
    });
    els.what.setAttribute('aria-activedescendant', items[activeOption].id);
    items[activeOption].scrollIntoView({ block: 'nearest' });
  }

  function choose(index) {
    var option = options[index];
    if (!option) return;
    hideList();
    if (option.create) { showCreate(option.create); return; }
    setWhat(option.item);
    els.what.value = option.item.name;
    document.getElementById('fm-error-what').hidden = true;
    els.what.removeAttribute('aria-invalid');
    els.what.focus();
  }

  function onWhatKey(event) {
    var open = !els.list.hidden;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!open) return;
      event.preventDefault();
      setActive(activeOption + (event.key === 'ArrowDown' ? 1 : -1));
    } else if (event.key === 'Enter' && open) {
      event.preventDefault();
      if (activeOption >= 0) choose(activeOption);
    } else if (event.key === 'Escape' && open) {
      event.preventDefault();
      hideList();
    }
  }

  function showCreate(name) {
    createName = name;
    els.unitLabel.textContent = interpolate(
      gettext('Unité de la nouvelle commodité « %(name)s »'), { name: name }, true);
    els.unitInput.value = '';
    els.create.hidden = false;
    els.unitInput.focus();
  }

  function hideCreate() {
    if (els.create) els.create.hidden = true;
  }

  function createCommodity() {
    if (busy) return;
    var p = document.getElementById('fm-error-what');
    p.hidden = true;
    setBusy(true);
    post(urls.commodityCreate, { name: createName, unit: els.unitInput.value.trim() })
      .then(function (res) {
        if (!res.ok) {
          var errors = (res.data && res.data.errors) || {};
          var messages = [];
          Object.keys(errors).forEach(function (k) { messages = messages.concat(errors[k]); });
          showErrors({ what: messages.length ? messages
            : [gettext('Erreur inattendue du serveur.')] });
          return;
        }
        setWhat(res.data);
        els.what.value = res.data.name;
        hideCreate();
        els.quantity.focus();
      })
      .catch(unexpected)
      .finally(function () { setBusy(false); });
  }

  function onUnitKey(event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      createCommodity();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      hideCreate();
      els.what.focus();
    }
  }

  // ── Fenêtre de confirmation ──────────────────────────────────────────────
  function confirm(message, opts) {
    opts = opts || {};
    if (pendingConfirm) finishConfirm(false);
    els.confirmMessage.textContent = message;
    els.confirmOk.textContent = opts.confirmLabel || gettext('Confirmer');
    els.confirmOk.classList.toggle('fm-dialog__ok--danger', opts.danger !== false);
    return new Promise(function (resolve) {
      pendingConfirm = { resolve: resolve, returnFocus: document.activeElement };
      els.dialog.showModal();
      els.confirmCancel.focus();
    });
  }

  function finishConfirm(result) {
    var pending = pendingConfirm;
    if (!pending) return;
    pendingConfirm = null;
    if (els.dialog.open) els.dialog.close();
    var back = pending.returnFocus;
    if (back && back.isConnected && typeof back.focus === 'function') back.focus();
    pending.resolve(result);
  }

  // Focus piégé entre les deux boutons (showModal rend déjà le reste inerte).
  function onDialogKey(event) {
    if (event.key !== 'Tab') return;
    var first = els.confirmCancel;
    var last = els.confirmOk;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    } else if (document.activeElement !== first && document.activeElement !== last) {
      event.preventDefault();
      first.focus();
    }
  }

  function bindDialog() {
    els.confirmOk.addEventListener('click', function () { finishConfirm(true); });
    els.confirmCancel.addEventListener('click', function () { finishConfirm(false); });
    els.dialog.addEventListener('cancel', function (event) {
      event.preventDefault();
      finishConfirm(false);
    });
    // « close » est asynchrone : celui d'une confirmation déjà résolue arrive
    // parfois après l'ouverture de la suivante (dialogue rouvert) et l'ignore.
    // Il ne compte que si le dialogue s'est fermé sans passer par nos boutons
    // (Échap répété, que le navigateur peut fermer sans « cancel »).
    els.dialog.addEventListener('close', function () {
      if (!els.dialog.open) finishConfirm(false);
    });
    els.dialog.addEventListener('keydown', onDialogKey);
    els.dialog.addEventListener('click', function (event) {
      if (event.target === els.dialog) finishConfirm(false);   // clic sur le fond
    });
  }

  // ── Initialisation ───────────────────────────────────────────────────────
  function onEscape(event) {
    if (event.key !== 'Escape' || event.defaultPrevented) return;
    if (els.dialog.open) return;
    if (els.menu && els.menu.contains(event.target)) return;
    if (trace) {
      event.preventDefault();
      cancelTrace();
      focusOpener();
    } else if (!els.panel.hidden) {
      event.preventDefault();
      close();
    }
  }

  function bindPanel() {
    els.form.addEventListener('submit', save);
    els.cancel.addEventListener('click', function () { close(); });
    els.closeButton.addEventListener('click', function () { close(); });
    els.remove.addEventListener('click', remove);
    els.add.addEventListener('click', function () {
      var edge = sheet && sheet.edge;
      if (edge) openNewFlow(edge.from, edge.to);
    });
    els.what.addEventListener('input', onWhatInput);
    els.what.addEventListener('keydown', onWhatKey);
    els.what.addEventListener('blur', hideList);
    els.list.addEventListener('mousedown', function (event) { event.preventDefault(); });
    els.unitInput.addEventListener('keydown', onUnitKey);
    els.createOk.addEventListener('click', createCommodity);
    els.createCancel.addEventListener('click', function () {
      hideCreate();
      els.what.focus();
    });
    els.traceUnknown.addEventListener('click', function () {
      if (trace) finishTrace(null);
    });
    els.traceCancel.addEventListener('click', function () {
      cancelTrace();
      focusOpener();
    });
    document.addEventListener('keydown', onEscape);
    document.addEventListener('flowmap:loaded', function () {
      cancelTrace();
      close({ focus: false });
      restoreFocus();
    });
    // Chargement échoué : plus rien de l'entreprise précédente ne reste actif.
    document.addEventListener('flowmap:cleared', function () {
      refocus = false;
      cancelTrace();
      close();
      // Le focus était sur un élément de la carte, retiré avec elle.
      if (document.activeElement === document.body) FlowMap.svg.focus({ preventScroll: true });
    });
  }

  // Après une écriture : le redessin a retiré l'élément focalisé, le focus revient
  // à l'ouvreur (ou à la carte) s'il n'est pas parti ailleurs entre-temps.
  function restoreFocus() {
    if (!refocus) return;
    refocus = false;
    var active = document.activeElement;
    if (!active || active === document.body) focusOpener();
  }

  // Après un redessin (groupe déplié ou replié…), la flèche qui porte le flux
  // ouvert reste en surbrillance tant que le panneau est ouvert.
  function keepHighlight(result) {
    if (!sheet || sheet.mode !== 'edit' || !sheet.flow || !result) return;
    var id = sheet.flow.id;
    var edge = result.edges.find(function (e) {
      return e.flows.some(function (f) { return f.id === id; });
    });
    if (!edge) return;
    opener = '.fm-edge[data-key="' + attr(edge.key) + '"]';
    if (FlowMap.state.selectedEdge === edge.key) return;
    FlowMap.state.selectedEdge = edge.key;
    var g = FlowMap.svg.querySelector(opener);
    if (g) g.classList.add('is-selected');
  }

  function init() {
    var panel = document.getElementById('flow-map-panel');
    if (!panel || !window.FlowMap || !window.FLOW_MAP_URLS) return;
    urls = FLOW_MAP_URLS;
    els = {
      panel: panel,
      title: document.getElementById('fm-panel-title'),
      closeButton: document.getElementById('fm-panel-close'),
      flows: document.getElementById('fm-panel-flows'),
      flowList: document.getElementById('fm-panel-flow-list'),
      form: document.getElementById('fm-panel-form'),
      route: document.getElementById('fm-panel-route'),
      errorAll: document.getElementById('fm-error-__all__'),
      kinds: document.getElementById('fm-panel-kinds'),
      what: document.getElementById('fm-what'),
      list: document.getElementById('fm-what-list'),
      create: document.getElementById('fm-what-create'),
      unitLabel: document.getElementById('fm-what-unit-label'),
      unitInput: document.getElementById('fm-what-unit'),
      createOk: document.getElementById('fm-what-create-ok'),
      createCancel: document.getElementById('fm-what-create-cancel'),
      unit: document.getElementById('fm-unit'),
      quantity: document.getElementById('fm-quantity'),
      year: document.getElementById('fm-year'),
      more: document.getElementById('fm-panel-more'),
      tier: document.getElementById('fm-tier'),
      scopeField: document.getElementById('fm-scope-field'),
      scope: document.getElementById('fm-scope'),
      source: document.getElementById('fm-source'),
      reference: document.getElementById('fm-reference'),
      save: document.getElementById('fm-save'),
      cancel: document.getElementById('fm-cancel'),
      remove: document.getElementById('fm-delete'),
      add: document.getElementById('fm-panel-add'),
      notice: document.getElementById('flow-map-notice'),
      menu: document.getElementById('flow-map-menu'),
      trace: document.getElementById('flow-map-trace'),
      traceText: document.getElementById('flow-map-trace-text'),
      traceUnknown: document.getElementById('flow-map-trace-unknown'),
      traceCancel: document.getElementById('flow-map-trace-cancel'),
      dialog: document.getElementById('flow-map-confirm'),
      confirmMessage: document.getElementById('flow-map-confirm-message'),
      confirmOk: document.getElementById('flow-map-confirm-ok'),
      confirmCancel: document.getElementById('flow-map-confirm-cancel'),
    };
    bindPanel();
    bindDialog();
    FlowMap.onTap.push(onTap);
    FlowMap.onRender.push(keepHighlight);
  }

  document.addEventListener('DOMContentLoaded', init);

  return {
    openNewFlow: openNewFlow,
    openEdge: openEdge,
    close: close,
    confirm: confirm,
  };
})();
