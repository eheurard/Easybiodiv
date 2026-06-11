/* Compare page — two-company metric comparison */

const compareState = { left: null, right: null };
let compareMetrics = [];

// Portal dropdown — single shared instance
let _portal         = null;
let _activeBlock    = null;

document.addEventListener('DOMContentLoaded', () => {
  const companies = JSON.parse(document.getElementById('companies-data').textContent);
  compareMetrics   = JSON.parse(document.getElementById('metrics-data').textContent);

  initCompareCombobox('left', companies);
  initCompareCombobox('right', companies);

  compareMetrics.slice(0, 2).forEach((m) => addBlock(m.key));

  document.getElementById('add-block-btn').addEventListener('click', () => {
    addBlock(getDefaultMetricKey());
  });

  // Close portal on outside click or scroll
  document.addEventListener('click',  (e) => {
    if (!_portal || _portal.hasAttribute('hidden')) return;
    const trigger = _activeBlock && _activeBlock.querySelector('.compare-metric-trigger');
    if (!_portal.contains(e.target) && (!trigger || !trigger.contains(e.target))) {
      closeDropdown();
    }
  }, true);

  document.addEventListener('scroll', () => { if (_activeBlock) repositionDropdown(); }, true);
});

// ── Combobox ──────────────────────────────────────────────────────────────────

function initCompareCombobox(side, companies) {
  const input    = document.getElementById(`company-search-${side}`);
  const listbox  = document.getElementById(`company-listbox-${side}`);
  const combobox = document.getElementById(`company-combobox-${side}`);
  if (!input || !listbox || !combobox) return;

  function renderOptions(query) {
    const q = query.toLowerCase();
    const filtered = companies.filter((c) => c.name.toLowerCase().includes(q));
    listbox.innerHTML = filtered
      .map((c) => `<li class="company-combobox__option" role="option" data-id="${c.id}" tabindex="-1">${escHtml(c.name)}</li>`)
      .join('');
    const open = filtered.length > 0;
    listbox.hidden = !open;
    combobox.setAttribute('aria-expanded', String(open));
  }

  function selectCompany(id, name) {
    input.value = name;
    listbox.hidden = true;
    combobox.setAttribute('aria-expanded', 'false');
    fetchCompanyData(side, id);
  }

  input.addEventListener('input',  () => renderOptions(input.value));
  input.addEventListener('focus',  () => renderOptions(input.value));

  listbox.addEventListener('click', (e) => {
    const opt = e.target.closest('[data-id]');
    if (opt) selectCompany(Number(opt.dataset.id), opt.textContent.trim());
  });

  document.addEventListener('click', (e) => {
    if (!combobox.contains(e.target)) {
      listbox.hidden = true;
      combobox.setAttribute('aria-expanded', 'false');
    }
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { listbox.hidden = true; combobox.setAttribute('aria-expanded', 'false'); }
    if (e.key === 'ArrowDown') { const f = listbox.querySelector('[data-id]'); if (f) { e.preventDefault(); f.focus(); } }
  });

  listbox.addEventListener('keydown', (e) => {
    const opts = [...listbox.querySelectorAll('[data-id]')];
    const idx  = opts.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' && idx < opts.length - 1) { e.preventDefault(); opts[idx + 1].focus(); }
    if (e.key === 'ArrowUp')  { e.preventDefault(); if (idx > 0) opts[idx - 1].focus(); else input.focus(); }
    if (e.key === 'Enter' && idx >= 0) selectCompany(Number(opts[idx].dataset.id), opts[idx].textContent.trim());
    if (e.key === 'Escape') { listbox.hidden = true; combobox.setAttribute('aria-expanded', 'false'); input.focus(); }
  });
}

// ── Data fetching ─────────────────────────────────────────────────────────────

function fetchCompanyData(side, pk) {
  const infoEl = document.getElementById(`company-info-${side}`);
  const card   = document.getElementById(`compare-card-${side}`);
  infoEl.innerHTML = '<p class="compare-company-info__loading"><span class="compare-loading-dot"></span>Chargement…</p>';
  card && card.classList.add('compare-col-card--loading');

  fetch(`${COMPARE_API_URL}${pk}/compare/`)
    .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then((data) => {
      compareState[side] = data;
      card && card.classList.remove('compare-col-card--loading');
      renderCompanyInfo(side, data);
      renderAllBlocks();
    })
    .catch((err) => {
      console.error('fetchCompanyData failed:', err);
      card && card.classList.remove('compare-col-card--loading');
      infoEl.innerHTML = '<p class="compare-company-info__error">Erreur de chargement</p>';
    });
}

// ── Company info card ─────────────────────────────────────────────────────────

function renderCompanyInfo(side, data) {
  const el = document.getElementById(`company-info-${side}`);
  el.innerHTML = `
    <div class="compare-company-info__name compare-company-info__name--in">${escHtml(data.company_name)}</div>
    <div class="compare-company-info__stat">${fmtNum(data.number_of_assets)} actif${data.number_of_assets !== 1 ? 's' : ''}</div>
  `;
}

// ── Blocks ────────────────────────────────────────────────────────────────────

function addBlock(metricKey) {
  if (!metricKey) return;
  const blocksEl = document.getElementById('compare-blocks');
  const block = createBlock(metricKey);
  block.style.opacity   = '0';
  block.style.transform = 'translateY(6px)';
  blocksEl.appendChild(block);
  requestAnimationFrame(() => {
    block.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
    block.style.opacity    = '1';
    block.style.transform  = 'translateY(0)';
  });
  renderBlock(block);
}

function createBlock(metricKey) {
  const metric = compareMetrics.find((m) => m.key === metricKey) || compareMetrics[0];

  const div = document.createElement('div');
  div.className      = 'compare-block';
  div.dataset.metric = metricKey;
  div.innerHTML = `
    <div class="compare-block__header">
      <button class="compare-metric-trigger" type="button" aria-haspopup="listbox" aria-expanded="false">
        <svg class="compare-metric-trigger__icon" width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
          <path d="M1.5 9.5L4.5 6.5l3 2 4-5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span class="compare-metric-trigger__label">${escHtml(metric.label)}</span>
        <svg class="compare-metric-trigger__chevron" width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M2.5 4.5l3 3 3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <button class="compare-block__remove" type="button" aria-label="Supprimer l'indicateur">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </button>
    </div>
    <div class="compare-block__values">
      <div class="compare-block__val compare-block__val--left">
        <div class="compare-block__val-number">—</div>
      </div>
      <div class="compare-block__val compare-block__val--right">
        <div class="compare-block__val-number">—</div>
      </div>
    </div>
    <div class="compare-block__bar" hidden>
      <div class="compare-block__bar-a"></div>
      <div class="compare-block__bar-b"></div>
    </div>
  `;

  div.querySelector('.compare-metric-trigger').addEventListener('click', (e) => {
    e.stopPropagation();
    _activeBlock === div ? closeDropdown() : openDropdown(div);
  });

  div.querySelector('.compare-block__remove').addEventListener('click', () => {
    if (_activeBlock === div) closeDropdown();
    div.style.transition = 'opacity 0.18s ease, transform 0.18s ease';
    div.style.opacity    = '0';
    div.style.transform  = 'scale(0.97)';
    setTimeout(() => div.remove(), 180);
  });

  return div;
}

// ── Portal dropdown ───────────────────────────────────────────────────────────

function ensurePortal() {
  if (!_portal) {
    _portal = document.createElement('div');
    _portal.className = 'compare-metric-dropdown';
    _portal.setAttribute('hidden', '');
    _portal.setAttribute('role', 'listbox');
    document.body.appendChild(_portal);

    _portal.addEventListener('keydown', (e) => {
      const opts = [..._portal.querySelectorAll('.compare-metric-option')];
      const fi   = opts.findIndex((o) => o === document.activeElement);
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (fi < opts.length - 1) opts[fi + 1].focus();
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (fi > 0) opts[fi - 1].focus();
        else _portal.querySelector('.compare-metric-search')?.focus();
      }
      if ((e.key === 'Enter' || e.key === ' ') && fi >= 0) {
        e.preventDefault();
        selectOption(opts[fi].dataset.key);
      }
      if (e.key === 'Escape') closeDropdown();
    });
  }
  return _portal;
}

function openDropdown(blockEl) {
  const portal  = ensurePortal();
  const trigger = blockEl.querySelector('.compare-metric-trigger');
  const current = blockEl.dataset.metric;

  _activeBlock = blockEl;

  portal.innerHTML = `
    <div class="compare-metric-search-wrap">
      <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
        <circle cx="5.5" cy="5.5" r="4" stroke="currentColor" stroke-width="1.3"/>
        <path d="M9 9l2.5 2.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
      </svg>
      <input class="compare-metric-search" type="text" placeholder="Filtrer…" autocomplete="off" aria-label="Filtrer les indicateurs">
    </div>
    <div class="compare-metric-options" role="listbox"></div>
  `;

  renderDropdownOptions(portal, current, '');

  portal.removeAttribute('hidden');
  trigger.setAttribute('aria-expanded', 'true');
  repositionDropdown();

  const searchInput = portal.querySelector('.compare-metric-search');
  searchInput.addEventListener('input', () => {
    renderDropdownOptions(portal, blockEl.dataset.metric, searchInput.value);
  });
  searchInput.addEventListener('keydown', (e) => {
    const opts = [...portal.querySelectorAll('.compare-metric-option')];
    if (e.key === 'ArrowDown') { e.preventDefault(); opts[0]?.focus(); }
    if (e.key === 'Escape')    closeDropdown();
  });

  requestAnimationFrame(() => searchInput.focus());
  portal.addEventListener('click', portalClickHandler);
}

function renderDropdownOptions(portal, currentKey, query) {
  const q    = query.toLowerCase().trim();
  const list = portal.querySelector('.compare-metric-options');
  const filtered = q
    ? compareMetrics.filter((m) => m.label.toLowerCase().includes(q))
    : compareMetrics;

  if (filtered.length === 0) {
    list.innerHTML = '<p class="compare-metric-empty">Aucun résultat</p>';
    return;
  }

  list.innerHTML = filtered.map((m) => {
    const active = m.key === currentKey;
    return `
      <div class="compare-metric-option${active ? ' compare-metric-option--active' : ''}"
           role="option" data-key="${m.key}" aria-selected="${active}" tabindex="-1">
        <span class="compare-metric-option__check" aria-hidden="true">
          ${active ? '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' : ''}
        </span>
        <span class="compare-metric-option__label">${escHtml(m.label)}</span>
      </div>`;
  }).join('');
}

function portalClickHandler(e) {
  const opt = e.target.closest('[data-key]');
  if (opt) selectOption(opt.dataset.key);
}

function selectOption(key) {
  if (!_activeBlock) return;
  const metric  = compareMetrics.find((m) => m.key === key);
  if (!metric) return;
  _activeBlock.dataset.metric = key;
  const label = _activeBlock.querySelector('.compare-metric-trigger__label');
  if (label) label.textContent = metric.label;
  renderBlock(_activeBlock);
  closeDropdown();
}

function closeDropdown() {
  if (!_portal) return;
  _portal.setAttribute('hidden', '');
  _portal.removeEventListener('click', portalClickHandler);
  if (_activeBlock) {
    const trigger = _activeBlock.querySelector('.compare-metric-trigger');
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
    _activeBlock = null;
  }
}

function repositionDropdown() {
  if (!_portal || !_activeBlock) return;
  const trigger = _activeBlock.querySelector('.compare-metric-trigger');
  if (!trigger) return;
  const r = trigger.getBoundingClientRect();
  const pw = _portal.offsetWidth || 240;
  let left = r.left + r.width / 2 - pw / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - pw - 8));
  _portal.style.top  = `${r.bottom + 6}px`;
  _portal.style.left = `${left}px`;
}

// ── Block rendering ───────────────────────────────────────────────────────────

function renderBlock(blockEl) {
  const key     = blockEl.dataset.metric;
  const leftEl  = blockEl.querySelector('.compare-block__val--left  .compare-block__val-number');
  const rightEl = blockEl.querySelector('.compare-block__val--right .compare-block__val-number');
  const barEl   = blockEl.querySelector('.compare-block__bar');
  const barA    = blockEl.querySelector('.compare-block__bar-a');
  const barB    = blockEl.querySelector('.compare-block__bar-b');

  const leftRaw  = compareState.left  !== null ? compareState.left[key]  : null;
  const rightRaw = compareState.right !== null ? compareState.right[key] : null;

  animateValueIn(leftEl,  leftRaw  !== null ? formatMetricValue(key, leftRaw)  : '—');
  animateValueIn(rightEl, rightRaw !== null ? formatMetricValue(key, rightRaw) : '—');

  if (barEl && barA && barB && leftRaw !== null && rightRaw !== null) {
    const total = leftRaw + rightRaw;
    if (total > 0) {
      const aPct = Math.round((leftRaw / total) * 100);
      barEl.removeAttribute('hidden');
      barA.style.width = `${aPct}%`;
      barB.style.width = `${100 - aPct}%`;
    } else {
      barEl.setAttribute('hidden', '');
    }
  } else if (barEl) {
    barEl.setAttribute('hidden', '');
  }
}

function animateValueIn(el, html) {
  el.style.transition = 'opacity 0.15s ease, transform 0.15s ease';
  el.style.opacity    = '0';
  el.style.transform  = 'translateY(4px)';
  requestAnimationFrame(() => setTimeout(() => {
    el.innerHTML    = html;
    el.style.opacity   = '1';
    el.style.transform = 'translateY(0)';
  }, 80));
}

function renderAllBlocks() {
  document.querySelectorAll('.compare-block').forEach(renderBlock);
}

// ── Formatting ────────────────────────────────────────────────────────────────

function formatMetricValue(key, value) {
  if (value === undefined || value === null) return '—';
  if (key === 'number_of_assets')       return fmtNum(value);
  if (key === 'total_lbiodiv')          return fmtEuro(value);
  if (key.startsWith('total_impact_'))  return fmtFootprint(value);
  if (key.startsWith('avg_dependency_'))
    return `${(value * 100).toLocaleString('fr-FR', { maximumFractionDigits: 1 })}&thinsp;%`;
  return String(value);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getDefaultMetricKey() {
  const used   = new Set([...document.querySelectorAll('.compare-block')].map((b) => b.dataset.metric));
  const unused = compareMetrics.find((m) => !used.has(m.key));
  return unused ? unused.key : compareMetrics[0].key;
}
