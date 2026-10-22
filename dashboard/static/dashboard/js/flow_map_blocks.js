'use strict';

// Blocs et groupes de la carte des flux (spec 2026-10-22 §5.3–§5.5, §6.2),
// Créateurs seulement.
//
//   Barre d'outils « + Pays / Région / Entreprise / Actif » : recherche serveur
//   (et création pour une entreprise ou un actif). Un actif « détenu par E »
//   crée une détention (part en %, à partir de l'année choisie, par défaut la fin
//   de la plage affichée) ; sinon le bloc
//   n'existe que pour la session (FlowMap.addSessionBlock) jusqu'à son premier flux.
//   « + Groupe d'actifs » et menu « ⋯ » d'un groupe : nom et membres, choisis
//   parmi les actifs de la carte ; un actif d'un autre groupe ne peut être coché.
//   Menu « ⋯ » d'un bloc : « Supprimer les liens » (aperçu chiffré du serveur sur
//   la plage, choix des années et de la fin de détention), « Retirer de la carte »
//   (bloc de session), « Modifier le groupe », « Supprimer le groupe ».
// Écritures suivies de « flowmap:changed » (rechargement de la carte).
window.FlowMapBlocks = (function () {
  var LINKABLE = ['asset', 'company', 'country', 'region'];
  var CREATABLE = ['asset', 'company'];
  var MAP_ZOOM = 1;
  var MAP_PICK_ZOOM = 5;
  var YEAR_MIN = 1900;       // bornes des années (YEAR_MIN / YEAR_MAX côté serveur)
  var YEAR_MAX = 2100;

  var els = {};
  var urls = {};
  var mode = null;           // 'add' | 'group' | null (panneau fermé)
  var add = null;            // {type, item, creating, created}
  var group = null;          // groupe modifié (entrée de model.groups) ou null (création)
  var country = null;        // pays choisi pour un nouvel actif {id, name}
  var region = null;         // région choisie (facultative)
  var opener = null;         // sélecteur (ou élément) à refocaliser à la fermeture
  var busy = false;          // écriture en cours : boutons désactivés jusqu'à sa fin
  var panelSeq = 0;          // numéro du panneau ouvert ; une réponse arrivée après
                             // sa fermeture (ou sa réouverture) ne le modifie pas
  var pendingReveal = null;  // clé du bloc à montrer après le rechargement
  var refocusMap = false;
  var minimap = null;
  var marker = null;
  var combos = {};

  // ── Utilitaires ──────────────────────────────────────────────────────────
  var idUrl = FlowMapUI.idUrl;
  var attr = FlowMapUI.cssEscape;

  function notice(message) {
    FlowMapPanel.notice(message);
  }

  function changed() {
    document.dispatchEvent(new CustomEvent('flowmap:changed'));
  }

  function focusKey() {
    var model = FlowMap.model();
    return model ? 'company:' + model.company.id : null;
  }

  function decimal(text) {
    var clean = String(text).trim().replace(/\s/g, '').replace(',', '.');
    if (!/^[-+]?(\d+\.?\d*|\.\d+)$/.test(clean)) return NaN;
    return parseFloat(clean);
  }

  function firstError(data, fallback) {
    var errors = (data && data.errors) || {};
    var all = [];
    Object.keys(errors).forEach(function (k) { all = all.concat(errors[k]); });
    return all[0] || fallback;
  }

  // ── Erreurs des formulaires ──────────────────────────────────────────────
  // Chaque champ serveur est relié à son message (<p id=…-error-champ>) et à son
  // contrôle ; les champs inconnus vont dans le message général du formulaire.
  function errorTarget(prefix, field) {
    var p = document.getElementById(prefix + '-error-' + field);
    return p ? field : '__all__';
  }

  function clearErrors(form) {
    form.querySelectorAll('.fm-panel__error').forEach(function (p) {
      p.textContent = '';
      p.hidden = true;
    });
    form.querySelectorAll('[aria-invalid]').forEach(function (input) {
      input.removeAttribute('aria-invalid');
    });
  }

  // errors : {champ: [messages]} ; inputs : {champ: élément} ; prefixes : {champ:
  // préfixe des id de message} (défaut : `prefix`).
  function showErrors(prefix, errors, inputs, prefixes) {
    var focus = null;
    var allId = prefix + '-error-__all__';
    Object.keys(errors).forEach(function (field) {
      var own = (prefixes && prefixes[field]) || prefix;
      var target = errorTarget(own, field);
      var p = document.getElementById(target === '__all__' ? allId : own + '-error-' + field);
      var text = [].concat(errors[field]).join(' ');
      p.textContent = p.textContent ? p.textContent + ' ' + text : text;
      p.hidden = false;
      var input = target === '__all__' ? null : inputs[field];
      if (input) {
        input.setAttribute('aria-invalid', 'true');
        if (!focus) focus = input;
      }
    });
    var all = document.getElementById(allId);
    if (focus) focus.focus();
    else if (!all.hidden) all.focus();
  }

  function setBusy(on) {
    busy = on;
    els.panel.setAttribute('aria-busy', on ? 'true' : 'false');
    els.panel.querySelectorAll('.fm-panel__actions button').forEach(function (b) {
      b.disabled = on;
    });
  }

  // ── Panneau ──────────────────────────────────────────────────────────────
  function showPanel(which, title, focusTarget) {
    document.dispatchEvent(new CustomEvent('flowmap:panelopen', { detail: { panel: 'block' } }));
    panelSeq += 1;
    mode = which;
    setBusy(busy);   // une écriture d'un panneau précédent peut être encore en route
    els.title.textContent = title;
    els.addForm.hidden = which !== 'add';
    els.groupForm.hidden = which !== 'group';
    els.panel.hidden = false;
    els.panel.scrollTop = 0;
    (focusTarget || els.panel).focus();
  }

  function focusOpener() {
    var target = typeof opener === 'string' ? FlowMap.svg.querySelector(opener) : opener;
    if (target && target.isConnected) target.focus({ preventScroll: true });
    else FlowMap.svg.focus({ preventScroll: true });
  }

  function close(opts) {
    if (els.panel.hidden) return;
    var active = document.activeElement;
    var hadFocus = !active || active === document.body || els.panel.contains(active);
    els.panel.hidden = true;
    panelSeq += 1;
    Object.keys(combos).forEach(function (k) { combos[k].cancel(); });
    mode = null;
    add = null;
    group = null;
    if (hadFocus && !(opts && opts.focus === false)) focusOpener();
  }

  // ── Ajout d'un bloc ──────────────────────────────────────────────────────
  var ADD_TITLES = {
    country: function () { return gettext('Ajouter un pays'); },
    region: function () { return gettext('Ajouter une région'); },
    company: function () { return gettext('Ajouter une entreprise'); },
    asset: function () { return gettext('Ajouter un actif'); },
  };
  var SEARCH_LABELS = {
    country: function () { return gettext('Pays'); },
    region: function () { return gettext('Région'); },
    company: function () { return gettext('Entreprise'); },
    asset: function () { return gettext('Actif'); },
  };

  function openAdd(type, button) {
    var model = FlowMap.model();
    if (!model) return;
    opener = button;
    add = { type: type, item: null, creating: false };
    clearErrors(els.addForm);
    els.searchLabel.textContent = SEARCH_LABELS[type]();
    els.search.value = '';
    combos.add.cancel();
    combos.add.set({ type: type, canCreate: CREATABLE.indexOf(type) >= 0 });
    els.createCompany.hidden = true;
    els.createAsset.hidden = true;
    els.own.hidden = type !== 'asset';
    els.ownCheck.checked = true;
    els.ownShare.value = '100';
    els.ownYear.value = String(model.end);
    els.ownLabel.textContent = interpolate(gettext('Détenu par %(company)s'),
      { company: model.company.name }, true);
    syncOwn();
    syncSubmit();
    showPanel('add', ADD_TITLES[type](), els.search);
  }

  function syncOwn() {
    els.ownShareField.hidden = !els.ownCheck.checked;
    els.ownYearField.hidden = !els.ownCheck.checked;
    els.ownHelp.hidden = !els.ownCheck.checked;
  }

  function syncSubmit() {
    els.addSubmit.textContent = add && add.creating
      ? gettext('Créer et ajouter') : gettext('Ajouter à la carte');
  }

  function onSearchInput() {
    if (add.item && els.search.value !== add.item.name) add.item = null;
  }

  function onSearchSelect(item) {
    add.item = item;
    stopCreate();
    var p = document.getElementById('fm-add-error-search');
    p.hidden = true;
    els.search.removeAttribute('aria-invalid');
    els.search.focus();
  }

  function startCreate(name) {
    add.item = null;
    add.creating = true;
    els.search.value = name;
    if (add.type === 'company') {
      els.createCompany.hidden = false;
      els.companyName.value = name;
      els.companyIsin.value = '';
      els.companyTicker.value = '';
      syncSubmit();
      els.companyName.focus();
    } else {
      els.createAsset.hidden = false;
      els.assetName.value = name;
      els.assetCountry.value = '';
      els.assetRegion.value = '';
      els.assetType.value = els.assetType.dataset.default;
      els.assetLat.value = '';
      els.assetLng.value = '';
      country = null;
      region = null;
      syncSubmit();
      initMinimap();
      els.assetName.focus();
    }
  }

  function stopCreate() {
    add.creating = false;
    els.createCompany.hidden = true;
    els.createAsset.hidden = true;
    syncSubmit();
  }

  function submitAdd(event) {
    event.preventDefault();
    if (busy || !add) return;
    clearErrors(els.addForm);
    var share = null;
    var start = null;
    if (add.type === 'asset' && els.ownCheck.checked) {
      share = decimal(els.ownShare.value);
      start = ownStartYear();
      var errors = {};
      if (!(share > 0 && share <= 100)) {
        errors.share = [gettext('Indiquez une part entre 0 et 100 %.')];
      }
      if (start === null) {
        errors.start_year = [interpolate(gettext('Saisissez une année entre %(min)s et '
          + '%(max)s.'), { min: String(YEAR_MIN), max: String(YEAR_MAX) }, true)];
      }
      if (Object.keys(errors).length) {
        showErrors('fm-add', errors, ownInputs(), OWN_PREFIXES);
        return;
      }
    }
    var ownership = share === null ? null : { share: share, start: start };
    var seq = panelSeq;
    if (add.creating) {
      (add.type === 'company' ? createCompany(seq) : createAsset(seq)).then(function (item) {
        if (item && seq === panelSeq) place(item, ownership, seq);   // panneau resté ouvert
      });
      return;
    }
    if (!add.item) {
      var message = CREATABLE.indexOf(add.type) >= 0
        ? gettext('Choisissez un élément dans la liste, ou créez-le.')
        : gettext('Choisissez un élément dans la liste.');
      showErrors('fm-add', { search: [message] }, { search: els.search });
      return;
    }
    place(add.item, ownership, seq);
  }

  // Champs de la détention : part et année de début (erreurs du serveur sous
  // `share` et `start_year`).
  var OWN_PREFIXES = { share: 'fm-own', start_year: 'fm-own' };

  function ownInputs() {
    return { share: els.ownShare, start_year: els.ownYear };
  }

  function ownStartYear() {
    var text = els.ownYear.value.trim();
    if (!/^[0-9]{4}$/.test(text)) return null;
    var year = parseInt(text, 10);
    return year >= YEAR_MIN && year <= YEAR_MAX ? year : null;
  }

  // Création réussie : l'élément devient le choix de la recherche, une nouvelle
  // tentative (détention refusée…) ne le recrée pas.
  function created(item, seq) {
    if (seq !== panelSeq) {
      // Panneau fermé entre-temps : l'élément existe, il se retrouve par la recherche.
      notice(interpolate(gettext('« %(name)s » a été créé ; recherchez-le pour l’ajouter.'),
        { name: item.name }, true));
      return null;
    }
    add.item = item;
    els.search.value = item.name;
    stopCreate();
    return item;
  }

  function write(url, payload) {
    setBusy(true);
    return FlowMapUI.post(url, payload).finally(function () { setBusy(false); });
  }

  function serverError() {
    return { __all__: [gettext('Erreur inattendue du serveur.')] };
  }

  function unexpected(prefix, seq) {
    return function (err) {
      console.error('flow_map block write failed:', err);
      var message = gettext('Le serveur est injoignable. Réessayez.');
      if (seq === panelSeq) showErrors(prefix, { __all__: [message] }, {});
      else notice(message);
      return null;
    };
  }

  function createCompany(seq) {
    return write(urls.companyCreate, {
      name: els.companyName.value.trim(),
      isin: els.companyIsin.value.trim(),
      ticker: els.companyTicker.value.trim(),
    }).then(function (res) {
      if (res.ok) return created(res.data, seq);
      if (seq !== panelSeq) return null;
      showErrors('fm-add', res.data.errors || serverError(), {
        name: els.companyName, isin: els.companyIsin, ticker: els.companyTicker,
      }, { name: 'fm-company', isin: 'fm-company', ticker: 'fm-company' });
      return null;
    }).catch(unexpected('fm-add', seq));
  }

  function createAsset(seq) {
    var inputs = {
      name: els.assetName, country: els.assetCountry, subnational_region: els.assetRegion,
      type: els.assetType, latitude: els.assetLat, longitude: els.assetLng,
    };
    var prefixes = {};
    Object.keys(inputs).forEach(function (k) { prefixes[k] = 'fm-asset'; });
    if (!country) {
      showErrors('fm-add', { country: [gettext('Choisissez un pays dans la liste.')] },
        inputs, prefixes);
      return Promise.resolve(null);
    }
    if (els.assetRegion.value.trim() && !region) {
      showErrors('fm-add', {
        subnational_region: [gettext('Choisissez une région dans la liste, ou laissez vide.')],
      }, inputs, prefixes);
      return Promise.resolve(null);
    }
    return write(urls.assetCreate, {
      name: els.assetName.value.trim(),
      country: country.id,
      subnational_region: region ? region.id : null,
      type: els.assetType.value,
      latitude: coordinate(els.assetLat.value),
      longitude: coordinate(els.assetLng.value),
    }).then(function (res) {
      if (res.ok) return created(res.data, seq);
      if (seq !== panelSeq) return null;
      showErrors('fm-add', res.data.errors || serverError(), inputs, prefixes);
      return null;
    }).catch(unexpected('fm-add', seq));
  }

  // Coordonnée saisie (virgule française acceptée) ; texte brut si illisible,
  // le serveur renvoie alors son message.
  function coordinate(text) {
    var value = decimal(text);
    return isNaN(value) ? String(text).trim() : value;
  }

  // ownership : {share (en %), start} pour un actif « détenu », sinon null. Une
  // détention qui chevaucherait une détention existante est refusée par le serveur
  // (l'actif peut n'être détenu qu'une partie de la plage affichée).
  function place(item, ownership, seq) {
    var model = FlowMap.model();
    if (!model) return;
    var key = add.type + ':' + item.id;
    if (add.type === 'asset' && ownership !== null) {
      own(item, ownership.share / 100, ownership.start, model, seq);
      return;
    }
    var name = item.name;
    var type = add.type;
    close({ focus: false });
    var result = FlowMap.addSessionBlock({ key: key, type: type, id: item.id, name: name });
    if (result === 'exists') {
      notice(interpolate(gettext('« %(name)s » est déjà sur la carte.'), { name: name }, true));
    } else if (result === 'added') {
      notice(interpolate(gettext('« %(name)s » ajouté pour cette session : tracez un flux '
        + 'pour l’enregistrer.'), { name: name }, true));
    }
  }

  function own(item, share, start, model, seq) {
    write(urls.ownershipCreate, {
      company_id: model.company.id,
      asset_id: item.id,
      share: share.toFixed(4),
      year: start,
    }).then(function (res) {
      if (!res.ok) {
        if (seq !== panelSeq) {
          notice(firstError(res.data, gettext('Erreur inattendue du serveur.')));
          return;
        }
        // part, année : sous leur champ ; entreprise, actif, chevauchement : en tête.
        showErrors('fm-add', res.data.errors || serverError(), ownInputs(), OWN_PREFIXES);
        return;
      }
      pendingReveal = 'asset:' + item.id;
      // Détention débutant après la plage affichée : l'élargir pour la montrer.
      if (start > model.end) FlowMap.includeYear(start);
      var message = interpolate(gettext('« %(name)s » ajouté au périmètre de %(company)s.'),
        { name: item.name, company: model.company.name }, true);
      if (seq === panelSeq) finish(message); else notice(message);
      changed();
    }).catch(unexpected('fm-add', seq));
  }

  function finish(message) {
    close({ focus: false });
    notice(message);
  }

  // ── Mini-carte (position d'un nouvel actif) ──────────────────────────────
  function initMinimap() {
    if (minimap) {
      requestAnimationFrame(function () { minimap.resize(); });
      return;
    }
    if (typeof maplibregl === 'undefined' || typeof mapStyleFor !== 'function') {
      els.map.hidden = true;
      els.mapHelp.textContent = gettext('Carte indisponible : saisissez la latitude et la '
        + 'longitude.');
      return;
    }
    minimap = new maplibregl.Map({
      container: els.map,
      style: mapStyleFor(activeMapStyleName()),
      center: [0, 20],
      zoom: MAP_ZOOM,
      attributionControl: { compact: true },
    });
    // Attribution repliée : sinon elle couvre la moitié de la mini-carte.
    minimap.on('load', function () {
      var attrib = els.map.querySelector('.maplibregl-ctrl-attrib');
      if (attrib) attrib.classList.remove('maplibregl-compact-show');
    });
    minimap.on('click', function (event) {
      var lat = Math.round(event.lngLat.lat * 1e5) / 1e5;
      var lng = Math.round(event.lngLat.lng * 1e5) / 1e5;
      els.assetLat.value = lat.toLocaleString(APP_LOCALE, { maximumFractionDigits: 5,
        useGrouping: false });
      els.assetLng.value = lng.toLocaleString(APP_LOCALE, { maximumFractionDigits: 5,
        useGrouping: false });
      [els.assetLat, els.assetLng].forEach(function (input) {
        input.removeAttribute('aria-invalid');
      });
      ['latitude', 'longitude'].forEach(function (f) {
        document.getElementById('fm-asset-error-' + f).hidden = true;
      });
      setMarker(lng, lat, false);
    });
    document.addEventListener('themechange', function () {
      if (minimap) minimap.setStyle(mapStyleFor(activeMapStyleName()));
    });
  }

  function setMarker(lng, lat, move) {
    if (!minimap) return;
    if (!marker) {
      var color = getComputedStyle(els.panel).getPropertyValue('--color-primary').trim();
      marker = new maplibregl.Marker(color ? { color: color } : {});
    }
    marker.setLngLat([lng, lat]).addTo(minimap);
    if (move) {
      minimap.easeTo({ center: [lng, lat], zoom: Math.max(minimap.getZoom(), MAP_PICK_ZOOM) });
    }
  }

  function onCoordinateInput() {
    var lat = decimal(els.assetLat.value);
    var lng = decimal(els.assetLng.value);
    if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) setMarker(lng, lat, true);
  }

  // ── Groupes ──────────────────────────────────────────────────────────────
  function groupOf(key) {
    var model = FlowMap.model();
    return model && model.groups.find(function (g) { return g.key === key; });
  }

  // Actifs de la carte (connus du serveur : un bloc de session n'est rattaché à
  // aucun groupe tant qu'il n'a pas de flux), triés par nom.
  function mapAssets(model) {
    return model.blocks.filter(function (b) {
      return b.type === 'asset' && !FlowMap.isSession(b.key);
    }).sort(function (a, b) { return a.name.localeCompare(b.name, APP_LOCALE); });
  }

  function openGroup(key, trigger) {
    var model = FlowMap.model();
    if (!model) return;
    opener = trigger;
    group = key ? groupOf(key) : null;
    if (key && !group) return;
    clearErrors(els.groupForm);
    els.groupName.value = group ? group.name : '';
    els.groupFilter.value = '';
    els.groupDelete.hidden = !group;
    renderMembers(model);
    showPanel('group', group ? gettext('Modifier le groupe') : gettext('Nouveau groupe d’actifs'),
      els.groupName);
  }

  function renderMembers(model) {
    els.members.textContent = '';
    var assets = mapAssets(model);
    if (!assets.length) {
      var empty = document.createElement('p');
      empty.className = 'fm-panel__help';
      empty.textContent = gettext('Aucun actif sur la carte. Ajoutez d’abord des actifs.');
      els.members.appendChild(empty);
    }
    assets.forEach(function (block) {
      var label = document.createElement('label');
      label.className = 'fm-member';
      label.dataset.name = fold(block.name);
      var input = document.createElement('input');
      input.type = 'checkbox';
      input.value = String(block.id);
      var inOther = block.group && (!group || block.group !== group.key);
      var other = inOther ? groupOf(block.group) : null;
      input.checked = !!group && block.group === group.key;
      input.disabled = !!other;
      var name = document.createElement('span');
      name.textContent = block.name;
      label.appendChild(input);
      label.appendChild(name);
      if (other) {
        label.classList.add('is-disabled');
        var note = document.createElement('span');
        note.className = 'fm-member__note';
        note.textContent = interpolate(gettext('déjà dans « %(group)s »'),
          { group: other.name }, true);
        label.appendChild(note);
      }
      els.members.appendChild(label);
    });
    var kept = keptMembers(model);
    els.groupKept.hidden = !kept.length;
    els.groupKept.textContent = interpolate(ngettext(
      '%(n)s autre actif du groupe, hors de cette liste, est conservé.',
      '%(n)s autres actifs du groupe, hors de cette liste, sont conservés.',
      kept.length), { n: kept.length.toLocaleString(APP_LOCALE) }, true);
  }

  // Membres du groupe modifié absents de la liste à cocher (hors de la carte cette
  // année, ou blocs de session) : renvoyés tels quels.
  function keptMembers(model) {
    if (!group) return [];
    var listed = new Set(mapAssets(model).map(function (b) { return b.key; }));
    return (group.all_members || group.members).filter(function (k) { return !listed.has(k); });
  }

  function fold(text) {
    return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  function filterMembers() {
    var q = fold(els.groupFilter.value.trim());
    els.members.querySelectorAll('.fm-member').forEach(function (label) {
      label.hidden = !!q && label.dataset.name.indexOf(q) < 0;
    });
  }

  function saveGroup(event) {
    event.preventDefault();
    var model = FlowMap.model();
    if (busy || !model) return;
    clearErrors(els.groupForm);
    var members = Array.prototype.map.call(
      els.members.querySelectorAll('input:checked'), function (i) { return Number(i.value); });
    keptMembers(model).forEach(function (k) { members.push(Number(k.split(':')[1])); });
    var inputs = { name: els.groupName };
    if (!members.length) {
      groupErrors({ members: [gettext('Cochez au moins un actif.')] }, inputs);
      return;
    }
    var seq = panelSeq;
    var editing = group;
    var url = editing ? idUrl(urls.groupUpdate, editing.id)
      : idUrl(urls.groupCreate, model.company.id);
    write(url, { name: els.groupName.value.trim(), members: members }).then(function (res) {
      var open = seq === panelSeq;
      if (res.status === 404) {
        var gone = firstError(res.data, gettext('Ce groupe n’existe plus.'));
        if (open) finish(gone); else notice(gone);
        changed();
        return;
      }
      if (!res.ok) {
        if (open) groupErrors(res.data.errors || serverError(), inputs);
        else notice(firstError(res.data, gettext('Erreur inattendue du serveur.')));
        return;
      }
      pendingReveal = 'group:' + res.data.id;
      var message = editing ? gettext('Groupe enregistré.') : gettext('Groupe créé.');
      if (open) finish(message); else notice(message);
      changed();
    }).catch(unexpected('fm-group', seq));
  }

  // Une erreur sur les membres marque la liste (fieldset) et donne le focus à sa
  // première case disponible, sauf si le nom, plus haut, est déjà en erreur.
  function groupErrors(errors, inputs) {
    showErrors('fm-group', errors, inputs);
    if (!errors.members) return;
    els.membersField.setAttribute('aria-invalid', 'true');
    if (errors.name) return;
    var box = els.members.querySelector('.fm-member:not([hidden]) input:not(:disabled)')
      || els.groupFilter;
    box.focus();
  }

  function deleteGroup(target) {
    var message = interpolate(gettext('Supprimer le groupe « %(name)s » ? Ses actifs et leurs '
      + 'flux restent sur la carte.'), { name: target.name }, true);
    var options = { confirmLabel: gettext('Supprimer') };
    return FlowMapPanel.confirm(message, options).then(function (ok) {
      if (!ok) return;
      return write(idUrl(urls.groupDelete, target.id), {}).then(function (res) {
        if (!res.ok && res.status !== 404) {
          notice(firstError(res.data, gettext('Erreur inattendue du serveur.')));
          return;
        }
        refocusMap = true;
        finish(res.ok ? gettext('Groupe supprimé.')
          : firstError(res.data, gettext('Ce groupe n’existe plus.')));
        changed();
      });
    }).catch(function (err) {
      console.error('flow_map group delete failed:', err);
      notice(gettext('Le serveur est injoignable. Réessayez.'));
    });
  }

  // ── Retrait des liens d'un bloc ──────────────────────────────────────────
  // Aperçu du serveur sur la plage affichée : années où des flux relient le bloc au
  // périmètre (nombre de flux par année), détention éventuelle d'un actif détenu,
  // copropriétaires. L'utilisateur choisit les années et la fin de détention.
  function unlinkOptions(node, preview, model) {
    var values = { name: node.name, company: model.company.name };
    var message = preview.years.length
      ? gettext('Supprimer les flux entre « %(name)s » et %(company)s pour les années :')
      : gettext('Aucun flux entre « %(name)s » et %(company)s sur cette plage.');
    var note = null;
    if (preview.co_owners && preview.co_owners.length) {
      note = interpolate(gettext('Ces flux disparaîtront aussi pour %(owners)s.'),
        { owners: preview.co_owners.join(', ') }, true);
    }
    return {
      message: interpolate(message, values, true),
      years: preview.years.map(function (entry) {
        return {
          year: entry.year,
          label: interpolate(ngettext('%(year)s — %(n)s flux', '%(year)s — %(n)s flux',
            entry.flows), { year: String(entry.year), n: entry.flows.toLocaleString(APP_LOCALE) },
          true),
        };
      }),
      // ownership_year n'a de sens que pour un actif détenu sur la plage.
      ownership: preview.ownership ? {
        company: model.company.name, year: preview.ownership_year,
        start: model.start, end: model.end,
      } : null,
      note: note,
      confirmLabel: gettext('Supprimer'),
    };
  }

  function unlink(node) {
    var model = FlowMap.model();
    if (!model) return;
    var url = idUrl(urls.unlink, model.company.id) + FlowMapUI.rangeQuery(model.start, model.end)
      + '&block=' + encodeURIComponent(node.key);
    FlowMapUI.getJson(url).then(function (res) {
      if (!res.ok) {
        notice(firstError(res.data, gettext('Erreur inattendue du serveur.')));
        return null;
      }
      var preview = res.data;
      if (!preview.years.length && !preview.ownership) {
        var none = model.start === model.end
          ? gettext('« %(name)s » n’a aucun lien à supprimer en %(year)s.')
          : gettext('« %(name)s » n’a aucun lien à supprimer de %(start)s à %(end)s.');
        notice(interpolate(none, {
          name: node.name, year: String(model.end), start: String(model.start),
          end: String(model.end),
        }, true));
        return null;
      }
      return FlowMapPanel.chooseYears(unlinkOptions(node, preview, model)).then(function (choice) {
        var now = FlowMap.model();
        if (!choice || !now || now.company.id !== model.company.id || now.start !== model.start
            || now.end !== model.end) {
          return null;
        }
        var body = { years: choice.years, ownership_year: choice.ownershipYear };
        return FlowMapUI.post(url, body).then(function (done) {
          if (!done.ok) {
            notice(firstError(done.data, gettext('Erreur inattendue du serveur.')));
            return;
          }
          refocusMap = true;
          notice(interpolate(gettext('Liens de « %(name)s » supprimés.'),
            { name: node.name }, true));
          changed();
        });
      });
    }).catch(function (err) {
      console.error('flow_map unlink failed:', err);
      notice(gettext('Le serveur est injoignable. Réessayez.'));
    });
  }

  function menuTrigger(key) {
    return '.fm-block[data-key="' + attr(key) + '"] .fm-block__menu';
  }

  function registerMenu() {
    FlowMap.menuActions.push({
      id: 'unlink',
      label: gettext('Supprimer les liens'),
      visible: function (node) {
        return FlowMap.canEdit && LINKABLE.indexOf(node.type) >= 0
          && node.key !== focusKey() && !FlowMap.isSession(node.key);
      },
      run: unlink,
    });
    FlowMap.menuActions.push({
      id: 'remove',
      label: gettext('Retirer de la carte'),
      visible: function (node) { return FlowMap.canEdit && FlowMap.isSession(node.key); },
      run: function (node) {
        FlowMap.removeSessionBlock(node.key);
        FlowMap.svg.focus({ preventScroll: true });
        notice(interpolate(gettext('« %(name)s » retiré de la carte.'), { name: node.name }, true));
      },
    });
    FlowMap.menuActions.push({
      id: 'group-edit',
      label: gettext('Modifier le groupe'),
      visible: function (node) { return FlowMap.canEdit && node.type === 'group'; },
      run: function (node) { openGroup(node.key, menuTrigger(node.key)); },
    });
    FlowMap.menuActions.push({
      id: 'group-delete',
      label: gettext('Supprimer le groupe'),
      visible: function (node) { return FlowMap.canEdit && node.type === 'group'; },
      run: function (node) {
        var target = groupOf(node.key);
        if (target) deleteGroup(target);
      },
    });
  }

  // ── Initialisation ───────────────────────────────────────────────────────
  function onEscape(event) {
    if (event.key !== 'Escape' || event.defaultPrevented || els.panel.hidden) return;
    var dialog = document.getElementById('flow-map-confirm');
    if (dialog && dialog.open) return;
    var menu = document.getElementById('flow-map-menu');
    if (menu && menu.contains(event.target)) return;
    event.preventDefault();
    close();
  }

  // Après une écriture : montrer le bloc concerné, ou rendre le focus à la carte
  // si l'élément focalisé a disparu avec le redessin.
  function onLoaded() {
    close({ focus: false });
    var key = pendingReveal;
    pendingReveal = null;
    if (key && FlowMap.reveal(key)) { refocusMap = false; return; }
    if (refocusMap && (!document.activeElement || document.activeElement === document.body)) {
      FlowMap.svg.focus({ preventScroll: true });
    }
    refocusMap = false;
  }

  function bind() {
    document.querySelectorAll('[data-add]').forEach(function (button) {
      button.addEventListener('click', function () {
        if (button.dataset.add === 'group') openGroup(null, button);
        else openAdd(button.dataset.add, button);
      });
    });
    els.closeButton.addEventListener('click', function () { close(); });
    els.addCancel.addEventListener('click', function () { close(); });
    els.groupCancel.addEventListener('click', function () { close(); });
    els.addForm.addEventListener('submit', submitAdd);
    els.groupForm.addEventListener('submit', saveGroup);
    els.groupDelete.addEventListener('click', function () {
      if (group && !busy) deleteGroup(group);
    });
    els.groupFilter.addEventListener('input', filterMembers);
    els.ownCheck.addEventListener('change', syncOwn);
    els.assetLat.addEventListener('change', onCoordinateInput);
    els.assetLng.addEventListener('change', onCoordinateInput);
    document.addEventListener('keydown', onEscape);
    document.addEventListener('flowmap:panelopen', function (event) {
      if (event.detail.panel !== 'block') close({ focus: false });
    });
    document.addEventListener('flowmap:loaded', onLoaded);
    document.addEventListener('flowmap:cleared', function () {
      pendingReveal = null;
      close();
    });
  }

  function bindCombos() {
    // Le type de la recherche suit le bouton qui a ouvert le panneau (openAdd).
    combos.add = FlowMapUI.combobox({
      input: els.search, list: els.addList, type: 'country', url: urls.search,
      canCreate: false, onSelect: onSearchSelect, onCreate: startCreate,
      onInput: onSearchInput,
    });
    combos.country = FlowMapUI.combobox({
      input: els.assetCountry, list: els.assetCountryList, type: 'country', url: urls.search,
      onSelect: function (item) { country = item; els.assetRegion.focus(); },
      onInput: function () {
        if (country && els.assetCountry.value !== country.name) country = null;
      },
    });
    combos.region = FlowMapUI.combobox({
      input: els.assetRegion, list: els.assetRegionList, type: 'region', url: urls.search,
      onSelect: function (item) { region = item; els.assetType.focus(); },
      onInput: function () {
        if (region && els.assetRegion.value !== region.name) region = null;
      },
    });
  }

  function init() {
    var panel = document.getElementById('flow-map-block-panel');
    if (!panel || !window.FlowMap || !window.FlowMapPanel || !window.FLOW_MAP_URLS) return;
    urls = FLOW_MAP_URLS;
    var $ = function (id) { return document.getElementById(id); };
    els = {
      panel: panel,
      title: $('fm-block-title'),
      closeButton: $('fm-block-close'),
      addForm: $('fm-add-form'),
      searchLabel: $('fm-add-search-label'),
      search: $('fm-add-search'),
      addList: $('fm-add-list'),
      createCompany: $('fm-create-company'),
      companyName: $('fm-company-name'),
      companyIsin: $('fm-company-isin'),
      companyTicker: $('fm-company-ticker'),
      createAsset: $('fm-create-asset'),
      assetName: $('fm-asset-name'),
      assetCountry: $('fm-asset-country'),
      assetCountryList: $('fm-asset-country-list'),
      assetRegion: $('fm-asset-region'),
      assetRegionList: $('fm-asset-region-list'),
      assetType: $('fm-asset-type'),
      map: $('fm-asset-map'),
      mapHelp: $('fm-asset-map-help'),
      assetLat: $('fm-asset-latitude'),
      assetLng: $('fm-asset-longitude'),
      own: $('fm-own'),
      ownCheck: $('fm-own-check'),
      ownLabel: $('fm-own-label'),
      ownShareField: $('fm-own-share-field'),
      ownShare: $('fm-own-share'),
      ownYearField: $('fm-own-year-field'),
      ownYear: $('fm-own-year'),
      ownHelp: $('fm-own-help'),
      addSubmit: $('fm-add-submit'),
      addCancel: $('fm-add-cancel'),
      groupForm: $('fm-group-form'),
      groupName: $('fm-group-name'),
      groupFilter: $('fm-group-filter'),
      members: $('fm-group-members'),
      membersField: $('fm-group-members-field'),
      groupKept: $('fm-group-kept'),
      groupSave: $('fm-group-save'),
      groupCancel: $('fm-group-cancel'),
      groupDelete: $('fm-group-delete'),
    };
    els.assetType.dataset.default = els.assetType.value;
    bindCombos();
    bind();
    registerMenu();
  }

  document.addEventListener('DOMContentLoaded', init);

  return { openAdd: openAdd, openGroup: openGroup, unlink: unlink };
})();
