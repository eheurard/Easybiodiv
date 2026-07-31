const CST_COMPANY_KEY = 'selected-company-id'; // partagé avec les pages de risque
const CST_DEBOUNCE_MS = 300;

const CST_COLORS = {
  baseline: '#dac1ba',
  transition: '#af5d43',
  physical: '#91452d',
  accent: '#feb87c',
};

const CST_STATE = {
  companyId: null,
  data: null,
  overrides: {},   // hypothèses surchargées par l'utilisateur
  charts: {},
  timer: null,
};

function cstPct(value, digits) {
  if (value === null || value === undefined) return '—';
  return (value * 100).toFixed(digits === undefined ? 2 : digits) + ' %';
}

function cstEuro(value) {
  if (value === null || value === undefined) return '—';
  return Math.round(value).toLocaleString('fr-FR') + ' €';
}

function cstBps(value) {
  if (value === null || value === undefined) return '—';
  const sign = value > 0 ? '+' : '';
  return sign + Math.round(value).toLocaleString('fr-FR') + ' pb';
}

/* ── Rendu ─────────────────────────────────────────────────────────────── */

function cstRenderScenarios(data) {
  const host = document.getElementById('cst-scenarios');
  host.innerHTML = '';
  const selected = data.selected ? data.selected.scenario : null;

  data.scenarios.forEach((scenario) => {
    const card = document.createElement('button');
    card.type = 'button';
    const isActive = scenario.key === selected;
    card.className = 'cst-scenario' + (isActive ? ' is-active' : '');
    card.setAttribute('role', 'radio');
    card.setAttribute('aria-checked', isActive ? 'true' : 'false');
    card.tabIndex = isActive ? 0 : -1;  // roving tabindex : un seul arrêt de tabulation
    card.dataset.key = scenario.key;
    card.innerHTML =
      '<span class="cst-scenario__name">' + escHtml(scenario.name) + '</span>' +
      '<span class="cst-scenario__family">' + escHtml(scenario.family_label) + '</span>' +
      '<span class="cst-scenario__warming">' +
      scenario.warming_c.toFixed(1).replace('.', ',') + ' °C</span>';
    card.title = scenario.narrative;
    card.addEventListener('click', () => {
      CST_STATE.overrides = { scenario: scenario.key };  // le scénario réinitialise
      cstRefresh();
    });
    host.appendChild(card);
  });

  // Aucun scénario sélectionné : le premier reste atteignable au clavier.
  if (!selected && host.children.length) {
    host.children[0].tabIndex = 0;
  }
}

function cstRenderHorizons(data) {
  const host = document.getElementById('cst-horizon');
  if (!data.horizon_curve.length) {
    // Pas de courbe (payload vide) : rien à afficher. Sortir ici est indispensable —
    // sans ce garde, le forEach ci-dessous ne peuple aucun enfant et l'appel
    // récursif de fin de fonction boucle indéfiniment (RangeError).
    host.innerHTML = '';
    return;
  }
  if (host.children.length) {
    Array.from(host.children).forEach((button) => {
      const active = data.selected && String(data.selected.horizon) === button.dataset.year;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-checked', active ? 'true' : 'false');
      button.tabIndex = active ? 0 : -1;  // roving tabindex
    });
    return;
  }
  data.horizon_curve.forEach((point) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'cst-segmented__btn';
    button.setAttribute('role', 'radio');
    button.dataset.year = String(point.year);
    button.textContent = String(point.year);
    button.addEventListener('click', () => {
      CST_STATE.overrides.horizon = point.year;
      delete CST_STATE.overrides.carbon_price; // le prix suit le nouvel horizon
      cstRefresh();
    });
    host.appendChild(button);
  });
  cstRenderHorizons(data);
}

/* ── Navigation clavier des radiogroups (roving tabindex) ─────────────────
   Un seul écouteur par groupe, posé une fois au chargement : il relit
   host.children à chaque pression de touche, donc il reste valide même
   après que cstRenderScenarios/cstRenderHorizons aient reconstruit le DOM. */

function cstBindRadioGroupKeyboard(hostId) {
  const host = document.getElementById(hostId);
  if (!host) return;
  host.addEventListener('keydown', (event) => {
    const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown';
    const backward = event.key === 'ArrowLeft' || event.key === 'ArrowUp';
    if (!forward && !backward) return;

    const items = Array.from(host.children);
    if (!items.length) return;
    const currentIndex = items.indexOf(document.activeElement);
    if (currentIndex === -1) return;

    event.preventDefault();
    const nextIndex = forward
      ? (currentIndex + 1) % items.length
      : (currentIndex - 1 + items.length) % items.length;
    items[nextIndex].focus();
    items[nextIndex].click();  // déclenche la même logique de sélection qu'un clic
  });
}

function cstRenderFields(data) {
  if (!data.selected) return;
  const selected = data.selected;

  document.getElementById('cst-carbon-price').value = Math.round(selected.carbon_price);
  document.getElementById('cst-ebitda-margin').value =
    (selected.ebitda_margin * 100).toFixed(1);
  document.getElementById('cst-pd-baseline').value =
    (selected.pd_baseline * 100).toFixed(3);

  const slider = document.getElementById('cst-pass-through');
  slider.value = Math.round(selected.pass_through * 100);
  document.getElementById('cst-pass-through-value').textContent =
    Math.round(selected.pass_through * 100) + ' %';

  document.getElementById('cst-scope3').checked = selected.include_scope3;
  document.getElementById('cst-scope3-hint').textContent =
    '(' + Math.round(selected.scope3_transmission * 100) + ' % du scope 3 amont retenu)';
}

function cstRenderKpis(data) {
  const result = data.result;
  document.getElementById('cst-pd-baseline-kpi').textContent =
    result ? cstPct(result.pd_baseline) : '—';
  document.getElementById('cst-pd-stressed-kpi').textContent =
    result ? cstPct(result.pd_stressed) : '—';
  document.getElementById('cst-delta-kpi').textContent =
    result ? cstBps(result.delta_bps) + ' (×' + result.multiple + ')' : '—';
  document.getElementById('cst-rating-kpi').textContent =
    result ? result.rating_baseline + ' → ' + result.rating_stressed : '—';
}

function cstRenderChannels(data) {
  const body = document.getElementById('cst-channels');
  body.innerHTML = '';
  if (!data.channels) return;

  const rows = [
    ['Transition (coût carbone)', data.channels.transition.cost_eur,
     data.channels.transition.pct_ebitda, data.channels.transition.shock_sigma],
    ['Physique (dommages)', data.channels.physical.loss_eur,
     data.channels.physical.pct_ebitda, data.channels.physical.shock_sigma],
  ];
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<th scope="row">' + row[0] + '</th>' +
      '<td class="data-tabular">' + cstEuro(row[1]) + '</td>' +
      '<td class="data-tabular">' + cstPct(row[2], 1) + '</td>' +
      '<td class="data-tabular">' + row[3].toFixed(3) + '</td>';
    body.appendChild(tr);
  });
}

function cstRenderAssumptions(data) {
  const body = document.getElementById('cst-assumptions');
  body.innerHTML = '';
  data.assumptions.forEach((row) => {
    const tr = document.createElement('tr');
    // label/value/source/reference viennent du backend et incluent des champs
    // éditables en admin (nom, source et référence du scénario) : échapper avant
    // toute insertion dans innerHTML.
    const rawSource = row.reference
      ? row.source + ' — ' + row.reference
      : row.source;
    const source = rawSource ? escHtml(rawSource) : '';
    tr.innerHTML =
      '<th scope="row">' + escHtml(row.label) + '</th>' +
      '<td class="data-tabular">' + escHtml(row.value) + '</td>' +
      '<td class="cst-source">' + (source || '—') + '</td>';
    body.appendChild(tr);
  });
}

function cstRenderWarnings(data) {
  const host = document.getElementById('cst-warnings');
  if (!data.warnings.length) {
    host.hidden = true;
    return;
  }
  host.hidden = false;
  host.textContent = data.warnings.join(' · ');
}

/* ── Graphiques ────────────────────────────────────────────────────────── */

function cstDestroy(name) {
  if (CST_STATE.charts[name]) {
    CST_STATE.charts[name].destroy();
    delete CST_STATE.charts[name];
  }
}

function cstRenderWaterfall(data) {
  cstDestroy('waterfall');
  if (!data.waterfall.length) return;
  const labels = data.waterfall.map((step) => step.label);
  const values = data.waterfall.map((step) => step.pd * 100);
  CST_STATE.charts.waterfall = new Chart(
    document.getElementById('cst-waterfall'),
    {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'PD (%)',
          data: values,
          backgroundColor: [CST_COLORS.baseline, CST_COLORS.transition,
                            CST_COLORS.physical],
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, title: { display: true, text: 'PD (%)' } } },
      },
    }
  );
}

function cstRenderHorizonChart(data) {
  cstDestroy('horizon');
  if (!data.horizon_curve.length) return;
  CST_STATE.charts.horizon = new Chart(
    document.getElementById('cst-horizon-chart'),
    {
      type: 'line',
      data: {
        labels: data.horizon_curve.map((point) => point.year),
        datasets: [{
          label: 'PD stressée (%)',
          data: data.horizon_curve.map(
            (point) => (point.pd === null ? null : point.pd * 100)
          ),
          borderColor: CST_COLORS.physical,
          backgroundColor: CST_COLORS.accent,
          tension: 0.25,
          fill: false,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, title: { display: true, text: 'PD (%)' } } },
      },
    }
  );
}

function cstRenderComparison(data) {
  cstDestroy('comparison');
  if (!data.scenario_comparison.length) return;
  const selected = data.selected ? data.selected.scenario : null;
  CST_STATE.charts.comparison = new Chart(
    document.getElementById('cst-comparison'),
    {
      type: 'bar',
      data: {
        labels: data.scenario_comparison.map((row) => row.name),
        datasets: [{
          label: 'PD stressée (%)',
          data: data.scenario_comparison.map(
            (row) => (row.pd === null ? null : row.pd * 100)
          ),
          backgroundColor: data.scenario_comparison.map(
            (row) => (row.key === selected ? CST_COLORS.physical : CST_COLORS.baseline)
          ),
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, title: { display: true, text: 'PD (%)' } } },
      },
    }
  );
}

function cstRender(data) {
  CST_STATE.data = data;
  // Un rendu qui échoue ne doit jamais empêcher l'appelant d'initialiser le
  // combobox juste après (sinon l'utilisateur reste bloqué sans pouvoir
  // changer d'entreprise pour se sortir d'un payload qui fait planter un
  // des rendus ci-dessous).
  try {
    cstRenderWarnings(data);
    cstRenderScenarios(data);
    cstRenderHorizons(data);
    cstRenderFields(data);
    cstRenderKpis(data);
    cstRenderChannels(data);
    cstRenderAssumptions(data);
    cstRenderWaterfall(data);
    cstRenderHorizonChart(data);
    cstRenderComparison(data);
  } catch (error) {
    console.error('cstRender a échoué :', error);
  }
}

/* ── Chargement ────────────────────────────────────────────────────────── */

function cstQueryString() {
  const params = new URLSearchParams();
  const overrides = CST_STATE.overrides;
  Object.keys(overrides).forEach((key) => {
    const value = overrides[key];
    if (value === null || value === undefined || value === false) return;
    params.set(key, value === true ? '1' : String(value));
  });
  const query = params.toString();
  return query ? '?' + query : '';
}

function cstApiUrl(companyId) {
  // Le template expose CLIMATE_STRESS_TEST_API_URL avec pk=0 ; même patron que
  // physical_risk.js.
  return CLIMATE_STRESS_TEST_API_URL.replace('/0/', '/' + companyId + '/')
    + cstQueryString();
}

function cstFetch() {
  if (!CST_STATE.companyId) return;
  fetch(cstApiUrl(CST_STATE.companyId))
    .then((response) => {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    })
    .then(cstRender)
    .catch(() => {
      const host = document.getElementById('cst-warnings');
      host.hidden = false;
      host.textContent = 'Le calcul a échoué. Vérifiez les hypothèses saisies.';
    });
}

function cstRefresh() {
  window.clearTimeout(CST_STATE.timer);
  CST_STATE.timer = window.setTimeout(cstFetch, CST_DEBOUNCE_MS);
}

function cstBindInputs() {
  document.getElementById('cst-carbon-price').addEventListener('input', (event) => {
    CST_STATE.overrides.carbon_price = event.target.value;
    cstRefresh();
  });
  document.getElementById('cst-ebitda-margin').addEventListener('input', (event) => {
    CST_STATE.overrides.ebitda_margin = Number(event.target.value) / 100;
    cstRefresh();
  });
  document.getElementById('cst-pd-baseline').addEventListener('input', (event) => {
    CST_STATE.overrides.pd_baseline = Number(event.target.value) / 100;
    cstRefresh();
  });
  const slider = document.getElementById('cst-pass-through');
  slider.addEventListener('input', (event) => {
    document.getElementById('cst-pass-through-value').textContent =
      event.target.value + ' %';
    CST_STATE.overrides.pass_through = Number(event.target.value) / 100;
    cstRefresh();
  });
  document.getElementById('cst-scope3').addEventListener('change', (event) => {
    CST_STATE.overrides.include_scope3 = event.target.checked;
    cstRefresh();
  });
  document.getElementById('cst-reset').addEventListener('click', () => {
    const scenario = CST_STATE.overrides.scenario;
    const horizon = CST_STATE.overrides.horizon;
    CST_STATE.overrides = {};
    if (scenario) CST_STATE.overrides.scenario = scenario;
    if (horizon) CST_STATE.overrides.horizon = horizon;
    cstRefresh();
  });
}

/* ── Combobox entreprise (même mécanisme que physical_risk.js) ─────────── */

function cstInitCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input = document.getElementById('company-search');
  const listbox = document.getElementById('company-listbox');
  const chevron = combobox && combobox.querySelector('.company-combobox__chevron');
  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

  function buildList(filter) {
    const query = filter.toLowerCase();
    listbox.innerHTML = companies
      .filter((c) => c.name.toLowerCase().includes(query))
      .map((c) =>
        '<li role="option" data-id="' + c.id + '" class="company-combobox__option'
        + (c.id === selected ? ' selected' : '') + '">' + escHtml(c.name) + '</li>')
      .join('');
  }
  function openList() {
    buildList(input.value);
    listbox.removeAttribute('hidden');
    combobox.setAttribute('aria-expanded', 'true');
    if (chevron) chevron.style.transform = 'rotate(180deg)';
  }
  function closeList() {
    listbox.setAttribute('hidden', '');
    combobox.setAttribute('aria-expanded', 'false');
    if (chevron) chevron.style.transform = '';
  }

  input.addEventListener('focus', openList);
  input.addEventListener('input', () => { buildList(input.value); openList(); });

  listbox.addEventListener('click', (event) => {
    const option = event.target.closest('[role="option"]');
    if (!option) return;
    selected = parseInt(option.dataset.id, 10);
    input.value = option.textContent;
    closeList();
    localStorage.setItem(CST_COMPANY_KEY, selected);
    CST_STATE.companyId = selected;
    CST_STATE.overrides = {};   // changer d'entreprise repart des valeurs par défaut
    cstFetch();
  });

  document.addEventListener('click', (event) => {
    if (!combobox.contains(event.target)) closeList();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeList();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialEl = document.getElementById('initial-data');
  const initialData = initialEl ? JSON.parse(initialEl.textContent) : null;

  cstBindInputs();
  cstBindRadioGroupKeyboard('cst-scenarios');
  cstBindRadioGroupKeyboard('cst-horizon');

  const savedId = parseInt(localStorage.getItem(CST_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some((c) => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    CST_STATE.companyId = savedId;
    fetch(cstApiUrl(savedId))
      .then((response) => {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then((data) => { cstRender(data); cstInitCombobox(companies, data); })
      .catch(() => cstInitCombobox(companies, initialData));
  } else {
    if (initialData) {
      CST_STATE.companyId = initialData.company_id;
      cstRender(initialData);
    }
    cstInitCombobox(companies, initialData);
  }
});
