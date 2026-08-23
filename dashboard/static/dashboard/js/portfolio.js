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
      gear.title = 'Détails financiers';
      gear.textContent = '⚙';
      if (r.instrument === 'BOND') { gear.classList.add('pf-gear--filled'); }
      gear.addEventListener('click', function () { openDialog(i); });
      tdGear.appendChild(gear);
      tr.appendChild(tdGear);

      var tdDel = document.createElement('td');
      var del = document.createElement('button');
      del.type = 'button';
      del.className = 'pf-del';
      del.title = 'Supprimer';
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
    $('pf-dialog-company').textContent = 'Détails — ' + r.companyName;
    $('pf-dlg-instrument').value = r.instrument;
    $('pf-dlg-bond-fields').hidden = r.instrument !== 'BOND';
    $('pf-dlg-maturity').value = r.maturity || '';
    $('pf-dlg-coupon').value = (r.coupon === null || r.coupon === undefined) ? '' : r.coupon;
    $('pf-dlg-facevalue').value = (r.faceValue === null || r.faceValue === undefined) ? '' : r.faceValue;
    $('pf-dialog').showModal();
  }

  // ── Impact tab ───────────────────────────────────────────────────
  function fmtNumber(v) {
    return Number(v || 0).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
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
            label: 'Impact financé (' + m.unit + ')',
            data: impacts,
            backgroundColor: '#af5d43',
            xAxisID: 'x',
            order: 2,
          },
          {
            label: 'Poids dans le portefeuille (%)',
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
            title: { display: true, text: 'Impact financé (' + m.unit + ')' },
          },
          xWeight: {
            position: 'top',
            beginAtZero: true,
            suggestedMax: 100,
            grid: { drawOnChartArea: false },
            title: { display: true, text: 'Poids (%)' },
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
  function physMix(a, b, t) {
    return {
      r: Math.round(a[0] + (b[0] - a[0]) * t),
      g: Math.round(a[1] + (b[1] - a[1]) * t),
      b: Math.round(a[2] + (b[2] - a[2]) * t),
    };
  }

  function physColor(score) {
    var s = Math.max(0, Math.min(1, Number(score) || 0));
    if (s < 0.5) { return physMix([26, 122, 76], [217, 154, 0], s / 0.5); }
    return physMix([217, 154, 0], [179, 38, 30], (s - 0.5) / 0.5);
  }

  function physLuminance(c) {
    return (0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b) / 255;
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
        $('pf-phys-empty').hidden = true;
        $('pf-phys-report').hidden = false;
        renderPhysical();
      });
  }

  function renderPhysical() {
    if (!PHYS_DATA) { return; }
    renderPhysRadar(PHYS_DATA);
    renderPhysHeatmap(PHYS_DATA);
  }

  function renderPhysRadar(data) {
    var canvas = $('pf-phys-radar');
    if (!canvas || typeof Chart === 'undefined') { return; }
    var labels = data.hazards.map(function (h) { return h.label; });
    var datasets = [{
      label: data.name || 'Portefeuille',
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

  function physRow(label, scores, hazards, isTotal) {
    var tr = document.createElement('tr');
    if (isTotal) { tr.className = 'pf-phys-row--total'; }
    var th = document.createElement('th');
    th.scope = 'row';
    th.textContent = label;
    tr.appendChild(th);
    scores.forEach(function (score, i) {
      var td = document.createElement('td');
      var col = physColor(score);
      td.style.backgroundColor = 'rgb(' + col.r + ',' + col.g + ',' + col.b + ')';
      td.style.color = physLuminance(col) > 0.55 ? '#1b1c19' : '#ffffff';
      td.textContent = Number(score).toFixed(2);
      td.title = hazards[i].label + ' : ' + Number(score).toFixed(2);
      tr.appendChild(td);
    });
    return tr;
  }

  function renderPhysHeatmap(data) {
    var table = $('pf-phys-heatmap');
    if (!table) { return; }
    table.innerHTML = '';
    var hazards = data.hazards;

    var thead = document.createElement('thead');
    var htr = document.createElement('tr');
    var corner = document.createElement('th');
    corner.scope = 'col';
    corner.textContent = 'Entreprise';
    htr.appendChild(corner);
    hazards.forEach(function (h) {
      var th = document.createElement('th');
      th.scope = 'col';
      th.textContent = h.label;
      htr.appendChild(th);
    });
    thead.appendChild(htr);
    table.appendChild(thead);

    var tbody = document.createElement('tbody');
    tbody.appendChild(physRow('Portefeuille', data.portfolio, hazards, true));
    data.companies.forEach(function (c) {
      tbody.appendChild(physRow(c.name, c.scores, hazards, false));
    });
    table.appendChild(tbody);
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
      style: 'https://tiles.openfreemap.org/styles/liberty',
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
      el.textContent = '▲ +' + pct + ' % vs benchmark';
    } else if (delta < 0) {
      el.classList.add('pf-trans-delta--better');
      el.textContent = '▼ −' + pct + ' % vs benchmark';
    } else {
      el.textContent = '= benchmark';
    }
  }

  function transUpdatePointsKpi() {
    var points = transPoints();
    $('pf-trans-points').textContent = points.length || '—';
    var label = TRANS_MODE === 'region' ? 'Régions'
      : (TRANS_MODE === 'country' ? 'Pays' : 'Assets');
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
      'Dette : ' + transFmt(point.total_lbiodiv) + '<br>' +
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
        status.textContent = 'Portefeuille enregistré.';
        status.className = 'pf-status pf-status--ok';
        fetchImpact(currentId);
        fetchPhysical(currentId);
        fetchTransition(currentId);
      } else {
        status.textContent = 'Erreur de validation. Vérifiez les champs.';
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
          : 'Portefeuille commun : lecture seule. Dupliquez-le pour le modifier.';
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
      status.textContent = 'La duplication a échoué.';
      status.className = 'pf-status pf-status--err';
    });
  }

  function addOwnedOption(id, name) {
    var select = $('pf-portfolio-select');
    var group = select.querySelector('optgroup[label="Mes portefeuilles"]');
    if (!group) {
      group = document.createElement('optgroup');
      group.label = 'Mes portefeuilles';
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
