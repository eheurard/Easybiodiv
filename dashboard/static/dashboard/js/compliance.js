'use strict';

const COMP_COMPANY_KEY = 'selected-company-id';

document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('comp-companies');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('comp-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  const select = document.getElementById('comp-company-select');
  if (select) {
    select.addEventListener('change', () => {
      const id = parseInt(select.value, 10);
      localStorage.setItem(COMP_COMPANY_KEY, String(id));
      compFetch(id);
    });
  }

  const savedId = parseInt(localStorage.getItem(COMP_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && (!initialData || savedId !== initialData.company_id)) {
    if (select) select.value = String(savedId);
    compFetch(savedId);
  } else {
    if (select && initialData) select.value = String(initialData.company_id);
    if (initialData) compRender(initialData);
  }
});

function compFetch(id) {
  fetch(COMP_API_URL.replace('/0/', '/' + id + '/'))
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(compRender)
    .catch(err => console.error('compliance fetch failed:', err));
}

function compEsc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function compRender(data) {
  // — Verrou de matérialité —
  const gate = document.getElementById('comp-materiality');
  gate.className = 'comp-gate comp-gate--' + data.materiality.status.toLowerCase();
  document.getElementById('comp-materiality-status').textContent =
    data.materiality.status_label;
  document.getElementById('comp-materiality-justif').textContent =
    data.materiality.justification || '';
  document.getElementById('comp-version').textContent = data.standard_version_label;

  // — KPIs —
  document.getElementById('comp-kpi-pct').textContent =
    data.synthesis.compliance_pct + ' %';
  const compliant = data.synthesis.counts_by_status.COMPLIANT || 0;
  document.getElementById('comp-kpi-compliant').textContent =
    compliant + ' / ' + data.synthesis.applicable_count;
  document.getElementById('comp-kpi-sites').textContent =
    data.e4_5_metric.sites_count;
  document.getElementById('comp-kpi-ha').textContent =
    data.e4_5_metric.total_area_ha;

  // — Frise LEAP —
  const leapEl = document.getElementById('comp-leap');
  leapEl.innerHTML = '';
  data.leap.forEach(p => {
    const item = document.createElement('div');
    item.className = 'comp-leap__item comp-leap__item--' + p.status.toLowerCase();
    item.innerHTML =
      '<div class="comp-leap__head">' +
        '<span class="comp-leap__phase">' + compEsc(p.label) + '</span>' +
        '<span class="comp-leap__status">' + compEsc(p.status_label) + '</span>' +
      '</div>' +
      '<p class="comp-leap__summary">' + compEsc(p.derived_summary) + '</p>' +
      (p.notes ? '<p class="comp-leap__notes">' + compEsc(p.notes) + '</p>' : '');
    leapEl.appendChild(item);
  });

  // — Non-matérialité vs détail DR —
  const notMat = document.getElementById('comp-not-material');
  const drEl = document.getElementById('comp-drs');
  if (data.materiality.status === 'NOT_MATERIAL') {
    document.getElementById('comp-not-material-text').textContent =
      data.materiality.justification ||
      'Aucune justification de non-matérialité saisie.';
    notMat.hidden = false;
    drEl.hidden = true;
    drEl.innerHTML = '';
    return;
  }
  notMat.hidden = true;
  drEl.hidden = false;

  // — Cartes DR —
  drEl.innerHTML = '';
  data.disclosure_requirements.forEach(dr => {
    const card = document.createElement('article');
    card.className = 'comp-dr';
    const cond = dr.is_conditional
      ? '<span class="comp-dr__cond">Conditionnel</span>' : '';
    const sugg = (dr.auto_suggestion && dr.auto_suggestion !== dr.status)
      ? '<p class="comp-dr__suggestion">Suggestion auto : ' +
        compEsc(dr.auto_suggestion) + '</p>'
      : '';
    const justif = dr.justification
      ? compEsc(dr.justification)
      : '<em>Aucune justification saisie</em>';
    card.innerHTML =
      '<header class="comp-dr__head">' +
        '<span class="comp-dr__code">' + compEsc(dr.code_label) + '</span>' +
        '<span class="comp-badge comp-badge--' + dr.status.toLowerCase() + '">' +
          compEsc(dr.status_label) + '</span>' +
        cond +
      '</header>' +
      '<h3 class="comp-dr__title">' + compEsc(dr.title) + '</h3>' +
      '<p class="comp-dr__desc">' + compEsc(dr.description) + '</p>' +
      '<p class="comp-dr__ref">Référence : ' + compEsc(dr.reference) + '</p>' +
      '<p class="comp-dr__justif">' + justif + '</p>' +
      sugg;
    drEl.appendChild(card);
  });
}
