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

  // ── Save / Load ──────────────────────────────────────────────────
  function save() {
    var payload = {
      id: currentId,
      name: $('pf-name').value,
      size: size(),
      currency_id: $('pf-currency').value || null,
      benchmark_id: $('pf-benchmark').value || null,
      is_benchmark: $('pf-is-benchmark').checked,
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
      });
  }

  function resetForm() {
    currentId = null;
    rows = [];
    $('pf-name').value = '';
    $('pf-size').value = 0;
    $('pf-currency').selectedIndex = 0;
    $('pf-benchmark').value = '';
    $('pf-is-benchmark').checked = false;
    $('pf-portfolio-select').value = '';
    $('pf-status').textContent = '';
    render();
  }

  function init() {
    initTabs();
    populateSelects();
    initCompanySearch();
    initDialog();
    $('pf-save-btn').addEventListener('click', save);
    $('pf-new-btn').addEventListener('click', resetForm);
    $('pf-portfolio-select').addEventListener('change', function (e) {
      if (e.target.value) { loadPortfolio(e.target.value); } else { resetForm(); }
    });
    render();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
