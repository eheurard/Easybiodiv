// ── Écran de chargement ─────────────────────────────────────────────────────
// Masque le loader une fois la page entièrement chargée. Fallback à 4 s pour
// ne jamais bloquer l'affichage si une ressource externe (carte, police) traîne.
(function () {
  function hideLoader() {
    const loader = document.getElementById('page-loader');
    if (loader) loader.classList.add('is-hidden');
  }
  if (document.readyState === 'complete') {
    hideLoader();
  } else {
    window.addEventListener('load', hideLoader);
    setTimeout(hideLoader, 4000);
  }
  // Retour via le cache bfcache (bouton précédent) : le loader doit rester masqué.
  window.addEventListener('pageshow', (e) => { if (e.persisted) hideLoader(); });
})();

const SATELLITE_STYLE = {
  version: 8,
  sources: {
    satellite: {
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      attribution: 'Tiles © Esri',
    },
  },
  layers: [{ id: 'satellite-bg', type: 'raster', source: 'satellite' }],
};

// Chaque fond a une variante par theme. « fiord » est le pendant sombre de
// « liberty » (style detaille), « dark » celui de « positron » (style gris).
// Le satellite ne change pas : l'imagerie est deja sombre.
const MAP_STYLES = {
  classic: {
    light: 'https://tiles.openfreemap.org/styles/liberty',
    dark: 'https://tiles.openfreemap.org/styles/fiord',
  },
  grayscale: {
    light: 'https://tiles.openfreemap.org/styles/positron',
    dark: 'https://tiles.openfreemap.org/styles/dark',
  },
  satellite: { light: SATELLITE_STYLE, dark: SATELLITE_STYLE },
};

function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

// Resout un nom de fond vers l'URL (ou l'objet) correspondant au theme actif.
// C'est le seul point d'entree : aucune page ne doit lire MAP_STYLES en direct.
function mapStyleFor(name) {
  const entry = MAP_STYLES[name] || MAP_STYLES.classic;
  return entry[currentTheme()];
}

// Nom du fond actuellement selectionne sur la page (bouton actif), ou
// « classic » quand la page n'expose pas de selecteur. Seuls les boutons de
// fond portent data-layer : la bascule supply chain partage .map-layer-btn.
function activeMapStyleName() {
  const btn = document.querySelector('.map-layer-btn--active[data-layer]');
  return (btn && btn.dataset.layer) || 'classic';
}

// Rejoue un fond sur une carte, puis appelle onReady une fois le NOUVEAU
// style en place (pour y reposer sources et couches). Avec un style chargé par
// URL, l'ancien style reste affiché et « chargé » pendant le téléchargement du
// nouveau : un « idle » peut alors survenir sur l'ancien (au moindre rendu), la
// reconstruction s'y fait trop tôt et le style qui arrive l'efface. On remplace
// donc le style d'un bloc (sans diff) et on attend « style.load », qui ne
// concerne que le nouveau style.
function replayMapStyle(map, style, onReady) {
  map.setStyle(style, { diff: false });
  map.once('style.load', onReady);
}

document.addEventListener('DOMContentLoaded', () => {

  // ── Sidebar toggle ──────────────────────────────────────────────────────
  const layout = document.getElementById('app-layout');
  const toggleBtn = document.getElementById('sidebar-toggle');

  if (layout && toggleBtn) {
    const STORAGE_KEY = 'sidebar-collapsed';
    const isCollapsed = localStorage.getItem(STORAGE_KEY) === '1';

    if (isCollapsed) applyCollapsed(true, false);

    toggleBtn.addEventListener('click', () => {
      const collapsed = layout.classList.toggle('sidebar-collapsed');
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
      toggleBtn.setAttribute('aria-expanded', String(!collapsed));
      toggleBtn.setAttribute('aria-label', collapsed ? 'Développer le menu' : 'Réduire le menu');
      if (collapsed) {
        document.querySelectorAll('.sidebar__nav-details').forEach(d => d.removeAttribute('open'));
      }
    });

    function applyCollapsed(collapsed, animate) {
      if (!animate) layout.style.transition = 'none';
      layout.classList.toggle('sidebar-collapsed', collapsed);
      toggleBtn.setAttribute('aria-expanded', String(!collapsed));
      toggleBtn.setAttribute('aria-label', collapsed ? 'Développer le menu' : 'Réduire le menu');
      if (collapsed) {
        document.querySelectorAll('.sidebar__nav-details').forEach(d => d.removeAttribute('open'));
      }
      if (!animate) requestAnimationFrame(() => { layout.style.transition = ''; });
    }
  }

  // ── Bascule jour / nuit ─────────────────────────────────────────────────
  // Le theme est deja pose par le script inline du <head> ; ici on ne gere
  // que le clic, la memorisation, et la diffusion aux cartes.
  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) {
    const syncBtn = () => {
      const dark = currentTheme() === 'dark';
      themeBtn.setAttribute('aria-pressed', String(dark));
      themeBtn.setAttribute('aria-label', dark ? 'Passer en mode jour' : 'Passer en mode nuit');
    };
    syncBtn();

    themeBtn.addEventListener('click', () => {
      const next = currentTheme() === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { /* stockage indisponible */ }
      syncBtn();
      // Les cartes ecoutent cet evenement pour rejouer leur fond.
      document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: next } }));
    });
  }

  // ── Legacy test button ──────────────────────────────────────────────────
  const testBtn = document.getElementById('test-btn');
  if (testBtn) {
    testBtn.addEventListener('click', () => {
      const isActive = testBtn.classList.toggle('active');
      testBtn.setAttribute('aria-pressed', String(isActive));
    });
  }

  // ── User menu dropdown ──────────────────────────────────────────────────
  const userMenuBtn = document.getElementById('user-menu-btn');
  const userDropdown = document.getElementById('user-dropdown');

  if (userMenuBtn && userDropdown) {
    function openMenu() {
      userDropdown.removeAttribute('hidden');
      userMenuBtn.setAttribute('aria-expanded', 'true');
    }
    function closeMenu() {
      userDropdown.setAttribute('hidden', '');
      userMenuBtn.setAttribute('aria-expanded', 'false');
    }

    userMenuBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      userDropdown.hasAttribute('hidden') ? openMenu() : closeMenu();
    });

    document.addEventListener('click', closeMenu);
    userDropdown.addEventListener('click', (e) => e.stopPropagation());
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeMenu(); userMenuBtn.focus(); }
    });
  }

});


function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtNum(n) {
  return Number(n).toLocaleString('fr-FR', { maximumFractionDigits: 0 });
}

function fmtEuro(n) {
  if (n >= 1e6) return `${(n / 1e6).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} M€`;
  if (n >= 1e3) return `${(n / 1e3).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} k€`;
  return `${n.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} €`;
}

function fmtFootprint(n) {
  if (n === 0) return '—';
  if (n >= 1e3) return `${(n / 1e3).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} k`;
  if (n >= 1) return n.toLocaleString('fr-FR', { maximumFractionDigits: 3 });
  const exp = Math.floor(Math.log10(Math.abs(n)));
  const mantissa = (n / Math.pow(10, exp)).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
  return `${mantissa}×10<sup>${exp}</sup>`;
}
