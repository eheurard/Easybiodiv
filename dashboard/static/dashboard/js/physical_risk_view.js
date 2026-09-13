'use strict';

// Rendu partagé du risque physique : bandes d'aléa, KPI, horizon, classement
// des aléas, tableau « Détail par actif », geojson des points, popup et
// légende. Les fonctions de rendu ciblent les identifiants des fragments
// _pr_panel.html et _pr_detail_drawer.html, inclus par la page Risque physique
// et par la Vue d'ensemble. Dépend de escHtml (main.js).
window.PhysicalRiskView = (function () {
  const BAND_COLORS = {
    Low:      '#dac1ba',
    Moderate: '#feb87c',
    High:     '#af5d43',
    Critical: '#91452d',
  };
  const BAND_LABELS = { Low: 'Faible', Moderate: 'Modéré', High: 'Élevé', Critical: 'Critique' };

  function band(score) {
    if (score >= 0.7) return 'Critical';
    if (score >= 0.5) return 'High';
    if (score >= 0.2) return 'Moderate';
    return 'Low';
  }

  function euro(v) {
    return Math.round(v).toLocaleString('fr-FR') + ' €';
  }

  function hazard(data, key) {
    if (!data || !key) return null;
    return (data.hazards || []).find(h => h.key === key) || null;
  }

  function renderKpis(data, horizon) {
    const highRisk = document.getElementById('pr-high-risk');
    if (highRisk) highRisk.textContent = data.kpis.assets_high_risk;
    const avgVuln = document.getElementById('pr-avg-vuln');
    if (avgVuln) {
      const av = data.kpis.avg_vulnerability;
      avgVuln.textContent = av != null ? (av * 100).toFixed(1) + '%' : '—';
    }
    renderLoss(data, horizon);
  }

  function renderLoss(data, horizon) {
    const el = document.getElementById('pr-annual-loss');
    if (!el || !data) return;
    const loss = data.kpis.annual_loss;
    el.textContent = loss != null ? euro(loss * horizon) : '—';
  }

  // Boutons 5 / 10 ans : état visuel, puis onChange(années).
  function bindHorizon(group, onChange) {
    if (!group) return;
    group.addEventListener('click', (e) => {
      const btn = e.target.closest('.pr-horizon__btn');
      if (!btn) return;
      group.querySelectorAll('.pr-horizon__btn').forEach(b => {
        const active = b === btn;
        b.classList.toggle('active', active);
        b.setAttribute('aria-pressed', String(active));
      });
      onChange(parseInt(btn.dataset.years, 10));
    });
  }

  // Classement des aléas ; il sert aussi de sélecteur : onSelect(clé) au clic.
  function renderRanking(data, selectedKey, onSelect) {
    const container = document.getElementById('pr-ranking');
    if (!container) return;
    if (!data.hazards || data.hazards.length === 0) {
      container.innerHTML = '<p class="pr-empty">Aucune donnée disponible.</p>';
      return;
    }
    const maxRisk = data.hazards.reduce((m, h) => h.avg_risk > m ? h.avg_risk : m, 0) || 1;
    container.innerHTML = data.hazards.map(h => {
      const pct = (h.avg_risk / maxRisk) * 100;
      const isSel = h.key === selectedKey;
      const sel = isSel ? ' pr-rank-row--selected' : '';
      return `
      <button type="button"
        class="pr-rank-row${sel}"
        data-key="${h.key}"
        aria-pressed="${isSel}">
        <span class="pr-rank-row__name">${escHtml(h.name)}</span>
        <span class="pr-rank-row__track">
          <span class="pr-rank-row__fill" style="width:${pct.toFixed(1)}%"></span>
        </span>
        <span class="pr-rank-row__val data-tabular">${euro(h.avg_risk)}</span>
      </button>`;
    }).join('');

    container.querySelectorAll('.pr-rank-row').forEach(row => {
      row.addEventListener('click', () => onSelect(row.dataset.key));
    });
  }

  function markSelected(key) {
    const container = document.getElementById('pr-ranking');
    if (!container) return;
    container.querySelectorAll('.pr-rank-row').forEach(row => {
      const active = row.dataset.key === key;
      row.classList.toggle('pr-rank-row--selected', active);
      row.setAttribute('aria-pressed', String(active));
    });
  }

  // Tableau « Détail par actif » pour l'aléa sélectionné.
  function renderTable(data, hazardKey) {
    const body = document.getElementById('pr-table-body');
    const hazardLabel = document.getElementById('pr-selected-hazard');
    if (!body) return;

    const current = hazard(data, hazardKey);
    if (hazardLabel) hazardLabel.textContent = current ? current.name : '—';

    if (!data || !current || data.assets.length === 0) {
      body.innerHTML = '<tr><td colspan="5" class="pr-empty">Aucun actif.</td></tr>';
      return;
    }

    const key = current.key;
    const vuln = current.vulnerability != null ? current.vulnerability : 0;
    const rows = data.assets.map(a => {
      const hz = a.risk[key] || 0;
      const risk = hz * a.exposition * vuln;
      return { name: a.name, hz: hz, expo: a.exposition, risk: risk,
               inventory: a.inventory || [] };
    }).sort((x, y) => y.risk - x.risk);

    const detail = current.vulnerability_detail || [];
    const detailRows = detail.length
      ? detail.map(d =>
          `<span class="pr-vuln-tooltip__row">
            <span class="pr-vuln-tooltip__policy">${escHtml(d.policy)}</span>
            <span class="pr-vuln-tooltip__val">${(d.value * 100).toFixed(1)}%</span>
          </span>`
        ).join('')
      : '<span class="pr-vuln-tooltip__note">Aucune politique renseignée</span>';

    body.innerHTML = rows.map(r => {
      const tooltip = `
        <span class="pr-vuln-tooltip" role="tooltip">
          <span class="pr-vuln-tooltip__title">Détail de la vulnérabilité</span>
          ${detailRows}
          <span class="pr-vuln-tooltip__result">Moyenne : ${(vuln * 100).toFixed(1)}%</span>
        </span>`;
      const invRows = r.inventory.map(e =>
        `<span class="pr-vuln-tooltip__row">
          <span class="pr-vuln-tooltip__policy">${escHtml(e.name)}</span>
          <span class="pr-vuln-tooltip__val">${e.value.toLocaleString('fr-FR')} ${escHtml(e.unit)}</span>
        </span>`).join('');
      const nameCell = r.inventory.length
        ? `<td class="pr-table__asset pr-table__asset--has-inv">${escHtml(r.name)}
            <span class="pr-inv-tooltip" role="tooltip">
              <span class="pr-vuln-tooltip__title">Inventaire mesuré</span>
              ${invRows}
            </span></td>`
        : `<td>${escHtml(r.name)}</td>`;
      return `
      <tr>
        ${nameCell}
        <td class="data-tabular">${(r.hz * 100).toFixed(1)}%</td>
        <td class="data-tabular">${euro(r.expo)}</td>
        <td class="data-tabular pr-table__vuln">${(vuln * 100).toFixed(1)}%${tooltip}</td>
        <td class="data-tabular pr-table__risk">${euro(r.risk)}</td>
      </tr>`;
    }).join('');
  }

  // Points : couleur par bande d'aléa, rayon proportionnel au risque en €.
  function buildGeojson(data, hazardKey) {
    const current = hazard(data, hazardKey);
    if (!data || !current) return { type: 'FeatureCollection', features: [] };

    const key = current.key;
    const vuln = current.vulnerability;
    const risks = data.assets.map(a => (a.risk[key] || 0) * a.exposition * vuln);
    const maxRisk = risks.reduce((m, v) => v > m ? v : m, 0) || 1;

    const features = data.assets.map((a, i) => {
      const hz = a.risk[key] || 0;
      const risk = risks[i];
      return {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [a.longitude, a.latitude] },
        properties: {
          name: a.name,
          hazardName: current.name,
          hazard: hz,
          exposition: a.exposition,
          risk: risk,
          radius: 6 + 18 * (risk / maxRisk),
          color: BAND_COLORS[band(hz)],
        },
      };
    });
    return { type: 'FeatureCollection', features: features };
  }

  function popupHtml(p) {
    return `
      <div class="asset-popup">
        <div class="asset-popup__header">
          <div class="asset-popup__name">${escHtml(p.name)}</div>
        </div>
        <div class="asset-popup__body">
          <div class="asset-popup__rows">
            <div class="asset-popup__row">
              <span class="asset-popup__row-label">${escHtml(p.hazardName)}</span>
              <span class="asset-popup__row-value">${(Number(p.hazard) * 100).toFixed(1)}%</span>
            </div>
            <div class="asset-popup__row">
              <span class="asset-popup__row-label">Exposition</span>
              <span class="asset-popup__row-value">${euro(Number(p.exposition))}</span>
            </div>
          </div>
          <div class="asset-popup__divider"></div>
          <div class="asset-popup__metrics">
            <div class="asset-popup__metric asset-popup__metric--risk">
              <div class="asset-popup__metric-value">${euro(Number(p.risk))}</div>
              <div class="asset-popup__metric-label">Risque</div>
            </div>
          </div>
        </div>
      </div>`;
  }

  function legendHtml() {
    const items = Object.keys(BAND_COLORS).map(k =>
      `<li><span class="map-legend__dot" style="background:${BAND_COLORS[k]}"></span>${BAND_LABELS[k]}</li>`
    ).join('');
    return `<p class="map-legend__title">Risque physique</p><ul class="map-legend__list">${items}</ul>`;
  }

  return {
    BAND_COLORS, band, hazard, renderKpis, renderLoss, bindHorizon, renderRanking,
    markSelected, renderTable, buildGeojson, popupHtml, legendHtml,
  };
})();
