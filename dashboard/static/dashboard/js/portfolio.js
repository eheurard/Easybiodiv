(function () {
  'use strict';

  function readJSON(id) {
    var el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : [];
  }

  function getCookie(name) {
    var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
  }

  var COMPANIES = readJSON('pf-companies');
  var CURRENCIES = readJSON('pf-currencies');
  var BENCHMARKS = readJSON('pf-benchmarks');

  // rows: {companyId, companyName, amount, weight, instrument, maturity, coupon, faceValue}
  var rows = [];
  var currentId = null;
  var dialogRowIndex = null;
  // Un portefeuille commun appartenant à quelqu'un d'autre est en lecture seule :
  // il se consulte et s'analyse, mais ne se modifie que via une duplication.
  var canEdit = true;

  // ── Impact tab state ─────────────────────────────────────────────
  var IMPACT_DATA = null;        // {metrics: {recipe, gbs}}
  var CURRENT_METRIC = 'recipe';
  var IMPACT_CHART = null;

  // ── Physical-risk tab state ──────────────────────────────────────
  var PHYS_DATA = null;          // {hazards, portfolio, benchmark, companies}
  var PHYS_CHART = null;

  // ── Transition-risk tab state ────────────────────────────────────
  var TRANS_DATA = null;        // réponse JSON complète
  var TRANS_MODE = 'asset';     // asset | region | country
  var TRANS_MAP = null;         // instance MapLibre (créée à la 1re activation)
  var TRANS_MARKERS = [];
  var TRANS_COLORS = {};        // {commodity_name: couleur} (via PieMarkers.colorMap)

  var $ = function (id) { return document.getElementById(id); };

  // Comparaison de l'impact financé à une ville (city_compare.js).
  var CITY = window.CityCompare
    ? CityCompare.create($('pf-city'), {
        fill: '#af5d43', line: '#ffd8c8',
        emptyMessage: gettext('Aucun impact à comparer pour ce portefeuille.'),
      })
    : null;

  // ── Tabs ────────────────────────────────────────────────────────
  function initTabs() {
    var tabs = document.querySelectorAll('.pf-tab');
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var name = tab.dataset.tab;
        tabs.forEach(function (t) {
          var active = t === tab;
          t.classList.toggle('pf-tab--active', active);
          t.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        document.querySelectorAll('.pf-panel').forEach(function (panel) {
          var active = panel.dataset.tabPanel === name;
          panel.classList.toggle('pf-panel--active', active);
          panel.hidden = !active;
        });
        if (name === 'impact' && CITY && IMPACT_DATA) { CITY.show(); }
        if (name === 'risque-physique' && PHYS_DATA) { physShowMap(); }
        if (name === 'risque-transition' && TRANS_DATA) {
          transEnsureMap();
          if (TRANS_MAP) {
            TRANS_MAP.resize();
            if (TRANS_MAP.loaded()) {
              transRenderMarkers();
            } else {
              TRANS_MAP.once('load', function () {
                TRANS_MAP.resize(); transRenderMarkers();
              });
            }
          }
        }
      });
    });
  }

  // ── Select population ────────────────────────────────────────────
  function populateSelects() {
    var cur = $('pf-currency');
    CURRENCIES.forEach(function (c) {
      var o = document.createElement('option');
      o.value = c.id;
      o.textContent = c.code + (c.symbol ? ' (' + c.symbol + ')' : '');
      cur.appendChild(o);
    });
    var bench = $('pf-benchmark');
    BENCHMARKS.forEach(function (b) {
      var o = document.createElement('option');
      o.value = b.id;
      o.textContent = b.name;
      bench.appendChild(o);
    });
  }

  // ── Company search ───────────────────────────────────────────────
  function initCompanySearch() {
    var input = $('pf-company-search');
    var listbox = $('pf-company-listbox');

    function close() { listbox.hidden = true; listbox.innerHTML = ''; }

    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase();
      listbox.innerHTML = '';
      if (!q) { close(); return; }
      var taken = rows.map(function (r) { return r.companyId; });
      var matches = COMPANIES.filter(function (c) {
        return c.name.toLowerCase().indexOf(q) !== -1 && taken.indexOf(c.id) === -1;
      }).slice(0, 8);
      if (!matches.length) { close(); return; }
      matches.forEach(function (c) {
        var li = document.createElement('li');
        li.className = 'pf-company-option';
        li.setAttribute('role', 'option');
        li.textContent = c.name;
        li.addEventListener('click', function () {
          addRow(c.id, c.name);
          input.value = '';
          close();
        });
        listbox.appendChild(li);
      });
      listbox.hidden = false;
    });

    document.addEventListener('click', function (e) {
      if (!input.contains(e.target) && !listbox.contains(e.target)) { close(); }
    });
  }

  // ── Rows ─────────────────────────────────────────────────────────
  function addRow(companyId, companyName, data) {
    data = data || {};
    rows.push({
      companyId: companyId,
      companyName: companyName,
      amount: data.amount || 0,
      weight: data.weight || 0,
      instrument: data.instrument || 'EQUITY',
      maturity: data.maturity || null,
      coupon: (data.coupon === undefined ? null : data.coupon),
      faceValue: (data.faceValue === undefined ? null : data.faceValue),
    });
    render();
  }

  function removeRow(i) { rows.splice(i, 1); render(); }

  function size() { return parseFloat($('pf-size').value) || 0; }

  function render() {
    var body = $('pf-holdings-body');
    body.innerHTML = '';
    rows.forEach(function (r, i) {
      var tr = document.createElement('tr');

      var tdName = document.createElement('td');
      tdName.textContent = r.companyName;
      tr.appendChild(tdName);

      var tdAmount = document.createElement('td');
      var amountInput = document.createElement('input');
      amountInput.type = 'number';
      amountInput.className = 'form-input pf-amount';
      amountInput.min = '0';
      amountInput.step = 'any';
      amountInput.value = r.amount;
      amountInput.addEventListener('input', function () {
        r.amount = parseFloat(amountInput.value) || 0;
        var s = size();
        r.weight = s > 0 ? (r.amount / s) * 100 : 0;
        updateRowWeight(i);
        updateTotals();
      });
      tdAmount.appendChild(amountInput);
      tr.appendChild(tdAmount);

      var tdWeight = document.createElement('td');
      var weightInput = document.createElement('input');
      weightInput.type = 'number';
      weightInput.className = 'form-input pf-weight';
      weightInput.min = '0';
      weightInput.max = '100';
      weightInput.step = 'any';
      weightInput.value = r.weight;
      weightInput.dataset.row = i;
      weightInput.addEventListener('input', function () {
        r.weight = parseFloat(weightInput.value) || 0;
        r.amount = (r.weight / 100) * size();
        amountInput.value = r.amount;
        updateTotals();
      });
      tdWeight.appendChild(weightInput);
      tr.appendChild(tdWeight);

      var tdGear = document.createElement('td');
      var gear = document.createElement('button');
      gear.type = 'button';
      gear.className = 'pf-gear';
      gear.title = gettext('Détails financiers');
      gear.textContent = '⚙';
      if (r.instrument === 'BOND') { gear.classList.add('pf-gear--filled'); }
      gear.addEventListener('click', function () { openDialog(i); });
      tdGear.appendChild(gear);
      tr.appendChild(tdGear);

      var tdDel = document.createElement('td');
      var del = document.createElement('button');
      del.type = 'button';
      del.className = 'pf-del';
      del.title = gettext('Supprimer');
      del.textContent = '🗑';
      del.addEventListener('click', function () { removeRow(i); });
      tdDel.appendChild(del);
      tr.appendChild(tdDel);

      body.appendChild(tr);
    });
    $('pf-empty').hidden = rows.length > 0;
    updateTotals();
    applyEditMode();
  }

  var EDITABLE_FIELDS = [
    'pf-name', 'pf-size', 'pf-currency', 'pf-benchmark', 'pf-is-benchmark',
    'pf-is-shared', 'pf-company-search', 'pf-save-btn',
  ];

  function applyEditMode() {
    var locked = !canEdit;
    EDITABLE_FIELDS.forEach(function (id) {
      var el = $(id);
      if (el) { el.disabled = locked; }
    });
    $('pf-holdings-body').querySelectorAll('input, button').forEach(function (el) {
      el.disabled = locked;
    });
    var dup = $('pf-duplicate-btn');
    if (dup) { dup.hidden = canEdit || !currentId; }
  }

  function updateRowWeight(i) {
    var input = document.querySelector('.pf-weight[data-row="' + i + '"]');
    if (input) { input.value = rows[i].weight; }
  }

  function updateTotals() {
    var amountTotal = rows.reduce(function (s, r) { return s + (r.amount || 0); }, 0);
    var weightTotal = rows.reduce(function (s, r) { return s + (r.weight || 0); }, 0);
    $('pf-amount-total').textContent = Math.round(amountTotal * 100) / 100;
    var wEl = $('pf-weight-total');
    wEl.textContent = (Math.round(weightTotal * 10) / 10) + ' %';
    wEl.classList.toggle('pf-total--ok', Math.abs(weightTotal - 100) < 0.5);
    wEl.classList.toggle('pf-total--warn', Math.abs(weightTotal - 100) >= 0.5);
  }

  // ── Dialog ───────────────────────────────────────────────────────
  function initDialog() {
    var dlg = $('pf-dialog');
    var instrument = $('pf-dlg-instrument');
    instrument.addEventListener('change', function () {
      $('pf-dlg-bond-fields').hidden = instrument.value !== 'BOND';
    });
    $('pf-dlg-cancel').addEventListener('click', function () { dlg.close(); });
    $('pf-dlg-validate').addEventListener('click', function () {
      var r = rows[dialogRowIndex];
      r.instrument = instrument.value;
      if (r.instrument === 'BOND') {
        r.maturity = $('pf-dlg-maturity').value || null;
        r.coupon = $('pf-dlg-coupon').value === '' ? null : parseFloat($('pf-dlg-coupon').value);
        r.faceValue = $('pf-dlg-facevalue').value === '' ? null : parseFloat($('pf-dlg-facevalue').value);
      } else {
        r.maturity = null; r.coupon = null; r.faceValue = null;
      }
      dlg.close();
      render();
    });
  }

  function openDialog(i) {
    dialogRowIndex = i;
    var r = rows[i];
    $('pf-dialog-company').textContent = gettext('Détails') + ' — ' + r.companyName;
    $('pf-dlg-instrument').value = r.instrument;
    $('pf-dlg-bond-fields').hidden = r.instrument !== 'BOND';
    $('pf-dlg-maturity').value = r.maturity || '';
    $('pf-dlg-coupon').value = (r.coupon === null || r.coupon === undefined) ? '' : r.coupon;
    $('pf-dlg-facevalue').value = (r.faceValue === null || r.faceValue === undefined) ? '' : r.faceValue;
    $('pf-dialog').showModal();
  }

  // ── Impact tab ───────────────────────────────────────────────────
  function fmtNumber(v) {
    return Number(v || 0).toLocaleString(APP_LOCALE, { maximumFractionDigits: 2 });
  }

  function clearImpact() {
    IMPACT_DATA = null;
    if (IMPACT_CHART) { IMPACT_CHART.destroy(); IMPACT_CHART = null; }
    $('pf-impact-report').hidden = true;
    $('pf-impact-empty').hidden = false;
  }

  function fetchImpact(pk) {
    fetch(PF_IMPACT_URL.replace('/0/impact/', '/' + pk + '/impact/'))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) { clearImpact(); return; }
        IMPACT_DATA = data;
        $('pf-impact-empty').hidden = true;
        $('pf-impact-report').hidden = false;
        renderImpact();
        var panel = document.querySelector('.pf-panel[data-tab-panel="impact"]');
        if (CITY && panel && !panel.hidden) { CITY.show(); }
      });
  }

  function setMetric(metric) {
    CURRENT_METRIC = metric;
    document.querySelectorAll('.pf-metric-btn').forEach(function (b) {
      var active = b.dataset.metric === metric;
      b.classList.toggle('pf-metric-btn--active', active);
      b.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    renderImpact();
  }

  function renderImpact() {
    if (!IMPACT_DATA) { return; }
    var m = IMPACT_DATA.metrics[CURRENT_METRIC];
    if (!m) { return; }
    $('pf-impact-total').textContent = fmtNumber(m.total);
    $('pf-impact-unit').textContent = m.unit;
    renderImpactChart(m);
    renderImpactCity(m);
  }

  // Surface en m² : PDF.m² tel quel, MSA.km² converti.
  function renderImpactCity(m) {
    if (!CITY) { return; }
    var m2 = /km²/.test(m.unit) ? m.total * 1e6 : m.total;
    var label = CURRENT_METRIC === 'gbs'
      ? gettext('Impact financé GBS (MSA·km²)') : gettext('Impact financé ReCiPe (PDF·m²)');
    CITY.setMeasures([{ key: CURRENT_METRIC, label: label, m2: m2 }], CURRENT_METRIC);
  }

  function renderImpactChart(m) {
    var canvas = $('pf-impact-chart');
    if (!canvas || typeof Chart === 'undefined') { return; }
    var names = m.companies.map(function (c) { return c.name; });
    var impacts = m.companies.map(function (c) { return c.weighted; });
    var weights = m.companies.map(function (c) { return { x: c.weight, y: c.name }; });

    if (IMPACT_CHART) { IMPACT_CHART.destroy(); }
    IMPACT_CHART = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: names,
        datasets: [
          {
            label: interpolate(gettext('Impact financé (%(unit)s)'), { unit: m.unit }, true),
            data: impacts,
            backgroundColor: '#af5d43',
            xAxisID: 'x',
            order: 2,
          },
          {
            label: gettext('Poids dans le portefeuille (%)'),
            type: 'scatter',
            data: weights,
            backgroundColor: '#865220',
            pointRadius: 5,
            pointHoverRadius: 6,
            xAxisID: 'xWeight',
            order: 1,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            position: 'bottom',
            beginAtZero: true,
            title: { display: true, text: interpolate(gettext('Impact financé (%(unit)s)'), { unit: m.unit }, true) },
          },
          xWeight: {
            position: 'top',
            beginAtZero: true,
            suggestedMax: 100,
            grid: { drawOnChartArea: false },
            title: { display: true, text: gettext('Poids (%)') },
          },
          y: { type: 'category' },
        },
        plugins: { legend: { position: 'bottom' } },
      },
    });
  }

  function initImpactToggle() {
    document.querySelectorAll('.pf-metric-btn').forEach(function (b) {
      b.addEventListener('click', function () { setMetric(b.dataset.metric); });
    });
  }

  // ── Physical-risk tab ────────────────────────────────────────────
  // Radar (profil pondéré par montant) et carte des actifs agrégés du
  // portefeuille, pondérés par l'exposition financée. La carte réutilise le
  // rendu de la page Risque physique (physical_risk_view.js) : classement des
  // aléas (sélecteur), perte projetée, points, popup et légende.
  var PHYS_MAP = null;
  var PHYS_MAP_READY = false;
  var PHYS_KEY = null;          // aléa sélectionné dans le classement
  var PHYS_HORIZON = 5;
  var PHYS_FIT = false;         // recadrer la carte sur les actifs au prochain rendu

  function physMapData() { return PHYS_DATA && PHYS_DATA.map; }

  function physPanelVisible() {
    var panel = document.querySelector('.pf-panel[data-tab-panel="risque-physique"]');
    return panel && !panel.hidden;
  }

  function clearPhysical() {
    PHYS_DATA = null;
    if (PHYS_CHART) { PHYS_CHART.destroy(); PHYS_CHART = null; }
    $('pf-phys-report').hidden = true;
    $('pf-phys-empty').hidden = false;
  }

  function fetchPhysical(pk) {
    fetch(PF_PHYSICAL_URL.replace('/0/physical-risk/', '/' + pk + '/physical-risk/'))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) { clearPhysical(); return; }
        PHYS_DATA = data;
        PHYS_FIT = true;
        $('pf-phys-empty').hidden = true;
        $('pf-phys-report').hidden = false;
        renderPhysical();
      });
  }

  function renderPhysical() {
    if (!PHYS_DATA) { return; }
    renderPhysRadar(PHYS_DATA);
    renderPhysMapPanel();
    if (physPanelVisible()) { physShowMap(); }
  }

  function renderPhysRadar(data) {
    var canvas = $('pf-phys-radar');
    if (!canvas || typeof Chart === 'undefined') { return; }
    var labels = data.hazards.map(function (h) { return h.label; });
    var datasets = [{
      label: data.name || gettext('Portefeuille'),
      data: data.portfolio,
      backgroundColor: 'rgba(175, 93, 67, 0.25)',
      borderColor: '#91452d',
      pointBackgroundColor: '#91452d',
    }];
    if (data.benchmark) {
      datasets.push({
        label: 'Benchmark',
        data: data.benchmark,
        backgroundColor: 'rgba(134, 82, 32, 0.15)',
        borderColor: '#865220',
        pointBackgroundColor: '#865220',
      });
    }
    if (PHYS_CHART) { PHYS_CHART.destroy(); }
    PHYS_CHART = new Chart(canvas.getContext('2d'), {
      type: 'radar',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { r: { beginAtZero: true, suggestedMin: 0, suggestedMax: 1 } },
        plugins: { legend: { position: 'bottom' } },
      },
    });
  }

  function renderPhysMapPanel() {
    var data = physMapData();
    if (!data || typeof PhysicalRiskView === 'undefined') { return; }
    var known = data.hazards.some(function (h) { return h.key === PHYS_KEY; });
    if (!known) { PHYS_KEY = data.hazards.length ? data.hazards[0].key : null; }
    PhysicalRiskView.renderKpis(data, PHYS_HORIZON);
    PhysicalRiskView.renderRanking(data, PHYS_KEY, physSelectHazard);
    var legend = $('pf-phys-legend');
    if (legend) { legend.innerHTML = PhysicalRiskView.legendHtml(); }
    var note = $('pf-phys-evic-note');
    if (note) {
      var missing = data.companies_without_evic || [];
      note.hidden = !missing.length;
      note.textContent = missing.length
        ? interpolate(gettext('Sans EVIC, exposition financée nulle : %(names)s.'),
            { names: missing.join(', ') }, true)
        : '';
    }
    physSyncMap();
  }

  function physSelectHazard(key) {
    PHYS_KEY = key;
    PhysicalRiskView.markSelected(key);
    physSyncMap();
  }

  function physAddLayers() {
    if (!PHYS_MAP.getSource('pf-phys-assets')) {
      PHYS_MAP.addSource('pf-phys-assets', {
        type: 'geojson', data: { type: 'FeatureCollection', features: [] },
      });
    }
    if (!PHYS_MAP.getLayer('pf-phys-layer')) {
      PHYS_MAP.addLayer({
        id: 'pf-phys-layer',
        type: 'circle',
        source: 'pf-phys-assets',
        paint: {
          'circle-radius': ['get', 'radius'],
          'circle-color': ['get', 'color'],
          'circle-opacity': 0.75,
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ffffff',
        },
      });
    }
  }

  // Recadre la carte sur l'ensemble des actifs (un seul : zoom régional).
  function physFitBounds(features) {
    if (!features.length) { return; }
    var lngs = features.map(function (f) { return f.geometry.coordinates[0]; });
    var lats = features.map(function (f) { return f.geometry.coordinates[1]; });
    PHYS_MAP.fitBounds(
      [[Math.min.apply(null, lngs), Math.min.apply(null, lats)],
       [Math.max.apply(null, lngs), Math.max.apply(null, lats)]],
      // Marge gauche : la légende occupe le coin inférieur gauche.
      { padding: { top: 50, right: 70, bottom: 50, left: 180 }, maxZoom: 6, duration: 0 }
    );
  }

  function physSyncMap() {
    if (!PHYS_MAP || !PHYS_MAP_READY || typeof PhysicalRiskView === 'undefined') { return; }
    var geojson = PhysicalRiskView.buildGeojson(physMapData(), PHYS_KEY);
    PHYS_MAP.getSource('pf-phys-assets').setData(geojson);
    if (PHYS_FIT) {
      PHYS_FIT = false;
      physFitBounds(geojson.features);
    }
  }

  // Création à la première ouverture de l'onglet : une carte créée dans un
  // panneau masqué n'a pas de taille.
  function physShowMap() {
    if (PHYS_MAP) {
      PHYS_MAP.resize();
      physSyncMap();
      return;
    }
    if (typeof maplibregl === 'undefined' || !$('pf-phys-map')) { return; }
    PHYS_MAP = new maplibregl.Map({
      container: 'pf-phys-map',
      style: mapStyleFor('classic'),
      center: [0, 20],
      zoom: 1.5,
    });
    // Carte dans une page qui défile : zoom par boutons, pas à la molette.
    PHYS_MAP.scrollZoom.disable();
    PHYS_MAP.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    PHYS_MAP.on('load', function () {
      physAddLayers();
      PHYS_MAP_READY = true;
      physSyncMap();
    });
    PHYS_MAP.on('click', 'pf-phys-layer', function (e) {
      new maplibregl.Popup()
        .setLngLat(e.lngLat)
        .setHTML(PhysicalRiskView.popupHtml(e.features[0].properties))
        .addTo(PHYS_MAP);
    });
    PHYS_MAP.on('mouseenter', 'pf-phys-layer', function () { PHYS_MAP.getCanvas().style.cursor = 'pointer'; });
    PHYS_MAP.on('mouseleave', 'pf-phys-layer', function () { PHYS_MAP.getCanvas().style.cursor = ''; });
  }

  function initPhysicalMap() {
    if (typeof PhysicalRiskView === 'undefined') { return; }
    PhysicalRiskView.bindHorizon(document.querySelector('#pf-phys-report .pr-horizon'), function (years) {
      PHYS_HORIZON = years;
      PhysicalRiskView.renderLoss(physMapData(), years);
    });
    // Le fond suit le thème : on rejoue le style puis on repose source et couche.
    document.addEventListener('themechange', function () {
      if (!PHYS_MAP) { return; }
      replayMapStyle(PHYS_MAP, mapStyleFor('classic'), function () {
        physAddLayers();
        physSyncMap();
      });
    });
  }

  // ── Transition risk (dette écologique financée) ──────────────────
  function fetchTransition(pk) {
    fetch(PF_TRANSITION_URL.replace('/0/transition-risk/', '/' + pk + '/transition-risk/'))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) { clearTransition(); return; }
        TRANS_DATA = data;
        $('pf-trans-empty').hidden = true;
        $('pf-trans-report').hidden = false;
        renderTransition();
      });
  }

  function clearTransition() {
    TRANS_DATA = null;
    transRemoveMarkers();
    $('pf-trans-report').hidden = true;
    $('pf-trans-empty').hidden = false;
  }

  function transRemoveMarkers() {
    TRANS_MARKERS.forEach(function (m) { m.remove(); });
    TRANS_MARKERS = [];
  }

  function transEnsureMap() {
    if (TRANS_MAP || typeof maplibregl === 'undefined') { return; }
    TRANS_MAP = new maplibregl.Map({
      container: 'pf-trans-map',
      style: mapStyleFor('classic'),
      center: [0, 20],
      zoom: 1.5,
    });
  }

  function renderTransition() {
    if (!TRANS_DATA) { return; }
    transBuildColorMap(TRANS_DATA.commodities);
    transRenderKpis(TRANS_DATA);
    transRenderLegend(TRANS_DATA.commodities);
    transEnsureMap();
    if (TRANS_MAP && TRANS_MAP.loaded()) {
      transRenderMarkers();
    } else if (TRANS_MAP) {
      TRANS_MAP.once('load', function () { TRANS_MAP.resize(); transRenderMarkers(); });
    }
  }

  function transBuildColorMap(commodities) {
    TRANS_COLORS = PieMarkers.colorMap(commodities);
  }

  function transPoints() {
    if (!TRANS_DATA) { return []; }
    if (TRANS_MODE === 'region') { return TRANS_DATA.regions; }
    if (TRANS_MODE === 'country') { return TRANS_DATA.countries; }
    return TRANS_DATA.assets;
  }

  function transRenderKpis(data) {
    $('pf-trans-total').textContent =
      data.total_lbiodiv ? transFmt(data.total_lbiodiv) : '—';
    $('pf-trans-companies').textContent = data.company_count || '—';
    $('pf-trans-top').textContent =
      data.commodities.length ? data.commodities[0].name : '—';
    transRenderDelta(data);
    transUpdatePointsKpi();
  }

  function transRenderDelta(data) {
    var el = $('pf-trans-delta');
    if (!el) { return; }
    var b = data.benchmark;
    if (!b || !b.total_lbiodiv) { el.hidden = true; return; }
    var delta = (data.total_lbiodiv - b.total_lbiodiv) / b.total_lbiodiv;
    var pct = (Math.abs(delta) * 100).toFixed(1);
    el.hidden = false;
    el.classList.remove('pf-trans-delta--worse', 'pf-trans-delta--better');
    if (delta > 0) {
      el.classList.add('pf-trans-delta--worse');
      el.textContent = '▲ +' + interpolate(gettext('%(pct)s % vs benchmark'), { pct: pct }, true);
    } else if (delta < 0) {
      el.classList.add('pf-trans-delta--better');
      el.textContent = '▼ −' + interpolate(gettext('%(pct)s % vs benchmark'), { pct: pct }, true);
    } else {
      el.textContent = '= benchmark';
    }
  }

  function transUpdatePointsKpi() {
    var points = transPoints();
    $('pf-trans-points').textContent = points.length || '—';
    var label = TRANS_MODE === 'region' ? gettext('Régions')
      : (TRANS_MODE === 'country' ? gettext('Pays') : gettext('Assets'));
    $('pf-trans-points-label').textContent = label;
  }

  function transRenderLegend(commodities) {
    var list = $('pf-trans-legend-list');
    if (!list) { return; }
    list.innerHTML = commodities.slice(0, 8).map(function (c) {
      var color = TRANS_COLORS[c.name] || '#ccc';
      return '<li class="de-legend__item">' +
        '<span class="de-legend__swatch" style="background:' + color + '"></span>' +
        '<span class="de-legend__name">' + transEsc(c.name) + '</span>' +
        '<span class="de-legend__pct">' + (c.pct * 100).toFixed(1) + '%</span>' +
        '</li>';
    }).join('');
  }

  function transRenderMarkers() {
    if (!TRANS_MAP) { return; }
    transRemoveMarkers();
    TRANS_MARKERS = PieMarkers.render(TRANS_MAP, transPoints(), TRANS_COLORS, {
      onEnter: transShowTooltip,
      onMove: transMoveTooltip,
      onLeave: transHideTooltip,
    });
  }

  function transShowTooltip(point, e) {
    var tip = $('pf-trans-tooltip');
    if (!tip) { return; }
    var top3 = point.commodities.slice(0, 3);
    tip.innerHTML = '<strong>' + transEsc(point.name) + '</strong><br>' +
      gettext('Dette :') + ' ' + transFmt(point.total_lbiodiv) + '<br>' +
      top3.map(function (c) {
        return '<span class="de-tooltip__swatch" style="background:' +
          (TRANS_COLORS[c.name] || '#ccc') + '"></span>' +
          transEsc(c.name) + ' : ' + (c.pct * 100).toFixed(1) + '%';
      }).join('<br>');
    tip.hidden = false;
    transMoveTooltip(e);
  }

  function transMoveTooltip(e) {
    var tip = $('pf-trans-tooltip'), mapEl = $('pf-trans-map');
    if (!tip || !mapEl) { return; }
    var rect = mapEl.getBoundingClientRect();
    tip.style.left = (e.clientX - rect.left + 14) + 'px';
    tip.style.top = (e.clientY - rect.top + 14) + 'px';
  }

  function transHideTooltip() {
    var tip = $('pf-trans-tooltip');
    if (tip) { tip.hidden = true; }
  }

  function transFmt(val) {
    if (val >= 1e9) { return '$' + (val / 1e9).toFixed(2) + ' G'; }
    if (val >= 1e6) { return '$' + (val / 1e6).toFixed(2) + ' M'; }
    if (val >= 1e3) { return '$' + (val / 1e3).toFixed(2) + ' k'; }
    return '$' + val.toFixed(2);
  }

  function transEsc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function initTransitionToggle() {
    document.querySelectorAll('.pf-trans-toggle__btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        TRANS_MODE = btn.dataset.mode;
        document.querySelectorAll('.pf-trans-toggle__btn').forEach(function (b) {
          var active = b === btn;
          b.classList.toggle('de-toggle__btn--active', active);
          b.setAttribute('aria-pressed', String(active));
        });
        if (TRANS_DATA) { transRenderMarkers(); transUpdatePointsKpi(); }
      });
    });
  }

  // ── Save / Load ──────────────────────────────────────────────────
  function save() {
    var payload = {
      id: currentId,
      name: $('pf-name').value,
      size: size(),
      currency_id: $('pf-currency').value || null,
      benchmark_id: $('pf-benchmark').value || null,
      is_benchmark: $('pf-is-benchmark').checked,
      is_shared: $('pf-is-shared') ? $('pf-is-shared').checked : false,
      holdings: rows.map(function (r) {
        return {
          company_id: r.companyId,
          amount: r.amount,
          weight: r.weight,
          instrument_type: r.instrument,
          maturity_date: r.maturity,
          coupon_rate: r.coupon,
          face_value: r.faceValue,
        };
      }),
    };
    fetch(PF_SAVE_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify(payload),
    }).then(function (resp) {
      return resp.json().then(function (data) { return { ok: resp.ok, data: data }; });
    }).then(function (res) {
      var status = $('pf-status');
      if (res.ok) {
        currentId = res.data.id;
        status.textContent = gettext('Portefeuille enregistré.');
        status.className = 'pf-status pf-status--ok';
        fetchImpact(currentId);
        fetchPhysical(currentId);
        fetchTransition(currentId);
      } else {
        status.textContent = gettext('Erreur de validation. Vérifiez les champs.');
        status.className = 'pf-status pf-status--err';
      }
    });
  }

  function loadPortfolio(pk) {
    fetch(PF_DETAIL_URL.replace(/0\/$/, pk + '/'))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        currentId = data.id;
        $('pf-name').value = data.name;
        $('pf-size').value = data.size;
        $('pf-currency').value = data.currency_id || '';
        $('pf-benchmark').value = data.benchmark_id || '';
        $('pf-is-benchmark').checked = !!data.is_benchmark;
        if ($('pf-is-shared')) { $('pf-is-shared').checked = !!data.is_shared; }
        canEdit = data.can_edit !== false;
        var status = $('pf-status');
        status.textContent = canEdit
          ? ''
          : gettext('Portefeuille commun : lecture seule. Dupliquez-le pour le modifier.');
        status.className = 'pf-status';
        rows = data.holdings.map(function (h) {
          return {
            companyId: h.company_id,
            companyName: h.company_name,
            amount: h.amount,
            weight: h.weight,
            instrument: h.instrument_type,
            maturity: h.maturity_date,
            coupon: h.coupon_rate,
            faceValue: h.face_value,
          };
        });
        render();
        fetchImpact(data.id);
        fetchPhysical(data.id);
        fetchTransition(data.id);
      });
  }

  function duplicate() {
    if (!currentId) { return; }
    fetch(PF_DUPLICATE_URL.replace('/0/', '/' + currentId + '/'), {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
    }).then(function (r) {
      if (!r.ok) { throw new Error('duplicate failed'); }
      return r.json();
    }).then(function (data) {
      addOwnedOption(data.id, data.name);
      $('pf-portfolio-select').value = data.id;
      loadPortfolio(data.id);
    }).catch(function () {
      var status = $('pf-status');
      status.textContent = gettext('La duplication a échoué.');
      status.className = 'pf-status pf-status--err';
    });
  }

  function addOwnedOption(id, name) {
    var select = $('pf-portfolio-select');
    var group = select.querySelector('optgroup[data-group="owned"]');
    if (!group) {
      group = document.createElement('optgroup');
      group.label = gettext('Mes portefeuilles');
      group.dataset.group = 'owned';
      select.insertBefore(group, select.children[1] || null);
    }
    var option = document.createElement('option');
    option.value = id;
    option.textContent = name;
    group.appendChild(option);
  }

  function resetForm() {
    currentId = null;
    canEdit = true;
    rows = [];
    $('pf-name').value = '';
    $('pf-size').value = 0;
    $('pf-currency').selectedIndex = 0;
    $('pf-benchmark').value = '';
    $('pf-is-benchmark').checked = false;
    if ($('pf-is-shared')) { $('pf-is-shared').checked = false; }
    $('pf-portfolio-select').value = '';
    $('pf-status').textContent = '';
    clearImpact();
    clearPhysical();
    clearTransition();
    render();
  }

  function init() {
    initTabs();
    populateSelects();
    initCompanySearch();
    initDialog();
    initImpactToggle();
    initPhysicalMap();
    initTransitionToggle();
    $('pf-save-btn').addEventListener('click', save);
    $('pf-new-btn').addEventListener('click', resetForm);
    $('pf-duplicate-btn').addEventListener('click', duplicate);
    $('pf-portfolio-select').addEventListener('change', function (e) {
      if (e.target.value) { loadPortfolio(e.target.value); } else { resetForm(); }
    });
    render();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
