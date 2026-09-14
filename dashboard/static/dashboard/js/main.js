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

  // ── Menu mobile (tiroir) ────────────────────────────────────────────────
  // Sous 768px, le rail d'icônes est remplacé par un tiroir ouvert depuis le
  // bouton ☰ du header. Le point de rupture doit rester aligné sur le CSS.
  const navOpenBtn = document.getElementById('nav-open-btn');
  const navCloseBtn = document.getElementById('nav-close-btn');
  const navBackdrop = document.getElementById('nav-backdrop');

  if (layout && navOpenBtn && navCloseBtn && navBackdrop) {
    const mobileQuery = window.matchMedia('(max-width: 768px)');

    function setNavOpen(open, restoreFocus) {
      // Dans le tiroir, le sous-menu « Analyse des risques » est toujours
      // déplié : sur les navigateurs sans ::details-content, un <details>
      // fermé masquerait ses liens quel que soit le CSS.
      if (open) document.querySelectorAll('.sidebar__nav-details').forEach(d => { d.open = true; });
      layout.classList.toggle('is-nav-open', open);
      navOpenBtn.setAttribute('aria-expanded', String(open));
      navBackdrop.hidden = !open;
      if (open) navCloseBtn.focus();
      else if (restoreFocus) navOpenBtn.focus();
    }

    navOpenBtn.addEventListener('click', () => setNavOpen(true));
    navCloseBtn.addEventListener('click', () => setNavOpen(false, true));
    navBackdrop.addEventListener('click', () => setNavOpen(false, true));
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && layout.classList.contains('is-nav-open')) setNavOpen(false, true);
    });
    // Passage en largeur desktop (rotation, redimensionnement) : on referme.
    mobileQuery.addEventListener('change', (e) => {
      if (!e.matches) setNavOpen(false, false);
    });
    // Retour arrière via le bfcache : la page revient avec le tiroir ouvert.
    window.addEventListener('pageshow', (e) => {
      if (e.persisted) setNavOpen(false, false);
    });
  }

  // ── Sélecteur de fond de carte replié (mobile) ──────────────────────────
  // Sur mobile, le groupe Classique / Gris / Satellite se replie derrière une
  // icône de calque et se déploie à l'horizontale au tap. Le CSS masque le
  // déclencheur sur desktop. Il ne porte pas .map-layer-btn : les scripts de
  // page ne le voient donc pas.
  const LAYER_ICON =
    '<svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">' +
    '<path d="M9 2.5L16 6.25 9 10 2 6.25 9 2.5z" stroke="currentColor" stroke-width="1.4" ' +
    'stroke-linejoin="round"/>' +
    '<path d="M2 9.25L9 13l7-3.75M2 12.25L9 16l7-3.75" stroke="currentColor" ' +
    'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  document.querySelectorAll('.map-layer-toggle').forEach((group) => {
    if (!group.querySelector('.map-layer-btn[data-layer]')) return;

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'map-layer-toggle__trigger';
    trigger.setAttribute('aria-label', 'Choisir le fond de carte');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.innerHTML = LAYER_ICON;
    group.prepend(trigger);
    group.classList.add('has-trigger');

    const setOpen = (open) => {
      group.classList.toggle('is-open', open);
      trigger.setAttribute('aria-expanded', String(open));
    };

    trigger.addEventListener('click', () => setOpen(!group.classList.contains('is-open')));
    // Un fond choisi : on replie (le script de page a déjà traité le clic).
    group.addEventListener('click', (e) => {
      if (e.target.closest('.map-layer-btn[data-layer]')) setOpen(false);
    });
    document.addEventListener('click', (e) => {
      if (!group.contains(e.target)) setOpen(false);
    });
  });

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
