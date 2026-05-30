const DEP_COMPANY_KEY = 'selected-company-id';

const SERVICE_ICONS = {
  water: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 3C10 3 4 9.5 4 13a6 6 0 0012 0c0-3.5-6-10-6-10z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
  </svg>`,
  soil_quality: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 15h14M3 11h14M3 7h14" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
  </svg>`,
  carbon_sequestration: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 17V7M10 7C10 7 7 4 4 5M10 7c0 0 3-3 6-2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`,
  water_purification: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M5 5h10l-2 5H7L5 5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
    <path d="M8 10v5M12 10v5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
  </svg>`,
  pest_control: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 3l6 3.5v7L10 17 4 13.5v-7L10 3z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
  </svg>`,
  pollination: `<svg class="dep-service-card__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="10" r="2.5" stroke="currentColor" stroke-width="1.4"/>
    <path d="M10 4v2M10 14v2M4 10h2M14 10h2M5.8 5.8l1.4 1.4M12.8 12.8l1.4 1.4M5.8 14.2l1.4-1.4M12.8 7.2l1.4-1.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
  </svg>`,
};

const REVENUE_ICON = `<svg class="dep-revenue-icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
  <rect x="3" y="5" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.4"/>
  <path d="M7 3v4M13 3v4M3 11h14" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
</svg>`;


document.addEventListener('DOMContentLoaded', () => {
  const companiesEl = document.getElementById('companies-data');
  if (!companiesEl) return;

  const companies = JSON.parse(companiesEl.textContent);
  const initialDataEl = document.getElementById('initial-data');
  const initialData = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;

  const savedId = parseInt(localStorage.getItem(DEP_COMPANY_KEY), 10);
  const savedExists = savedId && companies.some(c => c.id === savedId);

  if (savedExists && initialData && savedId !== initialData.company_id) {
    fetch(DEPENDENCIES_API_URL.replace('/0/', '/' + savedId + '/'))
      .then(r => r.json())
      .then(data => {
        renderDependencies(data);
        initDepCombobox(companies, data);
      });
  } else {
    if (initialData) renderDependencies(initialData);
    initDepCombobox(companies, initialData);
  }
});


function initDepCombobox(companies, initialData) {
  const combobox = document.getElementById('company-combobox');
  const input    = document.getElementById('company-search');
  const listbox  = document.getElementById('company-listbox');
  const chevron  = combobox && combobox.querySelector('.company-combobox__chevron');

  if (!combobox || !input || !listbox) return;

  let selected = initialData ? initialData.company_id : null;
  if (initialData) input.value = initialData.company_name;

  function buildList(filter) {
    const q = filter.toLowerCase();
    const matched = companies.filter(c => c.name.toLowerCase().includes(q));
    listbox.innerHTML = matched.map(c =>
      `<li role="option" data-id="${c.id}" class="company-combobox__option${c.id === selected ? ' selected' : ''}">${escHtml(c.name)}</li>`
    ).join('');
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

  input.addEventListener('focus', () => openList());
  input.addEventListener('input', () => { buildList(input.value); openList(); });

  listbox.addEventListener('click', (e) => {
    const opt = e.target.closest('[role="option"]');
    if (!opt) return;
    const id = parseInt(opt.dataset.id, 10);
    selected = id;
    input.value = opt.textContent;
    closeList();
    localStorage.setItem(DEP_COMPANY_KEY, id);
    fetch(DEPENDENCIES_API_URL.replace('/0/', '/' + id + '/'))
      .then(r => r.json())
      .then(data => renderDependencies(data));
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) closeList();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeList();
  });
}


function renderDependencies(data) {
  renderKPIs(data);
  renderSupplyChain(data.supply_chain || []);
  renderServiceExposure(data.service_exposure || {});
  renderRevenueSegments(data.revenue_segments || []);
}


function renderKPIs(data) {
  const globalScore = document.getElementById('dep-global-score');
  if (globalScore) {
    globalScore.textContent = data.global_exposure_score != null
      ? Math.round(data.global_exposure_score * 100) + ' %'
      : '—';
  }

  const criticalNodes = document.getElementById('dep-critical-nodes');
  if (criticalNodes) {
    criticalNodes.textContent = data.critical_nodes != null ? data.critical_nodes : '—';
  }

  const primaryService = document.getElementById('dep-primary-service');
  const primaryScore   = document.getElementById('dep-primary-score');
  if (primaryService) {
    primaryService.textContent = data.primary_service ? data.primary_service.name : '—';
  }
  if (primaryScore) {
    primaryScore.textContent = data.primary_service
      ? 'Score : ' + Math.round(data.primary_service.score * 100) + ' %'
      : '';
  }
}


function renderSupplyChain(tiers) {
  const body = document.getElementById('dep-supply-chain-body');
  if (!body) return;

  if (!tiers || tiers.length === 0) {
    body.innerHTML = '<p class="dep-empty">Aucune donnée de production disponible.</p>';
    return;
  }

  body.innerHTML = tiers.map(tier => {
    const cards = tier.services.map(svc => {
      const levelClass = svc.label.toLowerCase();
      const widthPct = Math.round(svc.score * 100);
      const icon = SERVICE_ICONS[svc.key] || '';
      return `
        <div class="dep-service-card">
          <div class="dep-service-card__top">
            ${icon}
            <span class="dep-service-card__name">${escHtml(svc.name)}</span>
          </div>
          <div class="dep-reliance-bar">
            <div class="dep-reliance-bar__fill dep-reliance-bar__fill--${levelClass}"
                 style="width:${widthPct}%"></div>
          </div>
          <span class="dep-service-card__label dep-service-card__label--${levelClass}">${escHtml(svc.label)}</span>
        </div>`;
    }).join('');

    return `
      <div class="dep-tier">
        <div class="dep-tier__header">
          <span class="dep-tier__bullet"></span>
          <span class="dep-tier__label">${escHtml(tier.label)}</span>
        </div>
        <hr class="dep-tier__divider">
        <div class="dep-service-grid">${cards}</div>
      </div>`;
  }).join('');
}


function renderServiceExposure(serviceExposure) {
  const body = document.getElementById('dep-service-exposure-body');
  if (!body) return;

  const categories = serviceExposure.categories || [];
  if (categories.length === 0) {
    body.innerHTML = '<p class="dep-empty">Aucune donnée disponible.</p>';
    return;
  }

  const maxScore = Math.max(
    ...categories.flatMap(cat => cat.services.map(s => s.score)),
    0.01
  );

  const cats = categories.map(cat => {
    const catAmount = cat.services.reduce((sum, s) => sum + (s.revenue_exposure || 0), 0);
    const amountDisplay = catAmount > 0
      ? formatRevenue(catAmount, serviceExposure.currency)
      : '';

    const rows = cat.services.map(svc => {
      const widthPct = Math.round((svc.score / maxScore) * 100);
      const amountStr = svc.revenue_exposure != null
        ? formatRevenue(svc.revenue_exposure, serviceExposure.currency)
        : '';
      return `
        <div class="dep-exposure-service-row">
          <span class="dep-exposure-service-name">${escHtml(svc.name)}</span>
          <div class="dep-exposure-bar-track">
            <div class="dep-exposure-bar-fill" style="width:${widthPct}%"></div>
          </div>
          <span class="dep-exposure-amount">${escHtml(amountStr)}</span>
        </div>`;
    }).join('');

    return `
      <div class="dep-exposure-category">
        <div class="dep-exposure-cat-header">
          <span class="dep-exposure-cat-name">${escHtml(cat.name)}</span>
          ${amountDisplay ? `<span class="dep-exposure-cat-amount">${escHtml(amountDisplay)}</span>` : ''}
        </div>
        ${rows}
      </div>`;
  }).join('');

  const note = serviceExposure.total_revenue != null
    ? '<div class="dep-exposure-note">Valeurs indicatives basées sur le revenu total de l\'entreprise.</div>'
    : '';

  body.innerHTML = cats + note;
}


function renderRevenueSegments(segments) {
  const body = document.getElementById('dep-revenue-segments-body');
  if (!body) return;

  if (!segments || segments.length === 0) {
    body.innerHTML = '<p class="dep-empty">Aucune donnée de revenu par segment.</p>';
    return;
  }

  const maxRevenue = Math.max(...segments.map(s => s.revenue), 1);

  body.innerHTML = segments.map(seg => {
    const widthPct = Math.round((seg.revenue / maxRevenue) * 100);
    const levelClass = seg.exposure_label.toLowerCase();
    const revenueStr = formatRevenue(seg.revenue, null);
    return `
      <div class="dep-revenue-row">
        ${REVENUE_ICON}
        <div class="dep-revenue-meta">
          <div class="dep-revenue-subsector">${escHtml(seg.subsector)}</div>
          <div class="dep-revenue-sector">${escHtml(seg.sector)}</div>
        </div>
        <div class="dep-revenue-bar-wrap">
          <div class="dep-revenue-bar-track">
            <div class="dep-revenue-bar-fill dep-revenue-bar-fill--${levelClass}"
                 style="width:${widthPct}%"></div>
          </div>
        </div>
        <span class="dep-revenue-amount">${escHtml(revenueStr)}</span>
        <span class="dep-exposure-badge dep-exposure-badge--${levelClass}">${escHtml(seg.exposure_label)}</span>
      </div>`;
  }).join('');
}


function formatRevenue(amount, currency) {
  if (amount == null) return '—';
  const sym = currency === 'EUR' ? '€' : (currency ? currency + ' ' : '');
  const abs = Math.abs(amount);
  if (abs >= 1e9) return sym + (amount / 1e9).toFixed(1) + 'Md';
  if (abs >= 1e6) return sym + (amount / 1e6).toFixed(1) + 'M';
  if (abs >= 1e3) return sym + (amount / 1e3).toFixed(0) + 'k';
  return sym + amount.toLocaleString('fr-FR');
}
